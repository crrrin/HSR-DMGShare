"""Experimental displayed-action damage attribution. No webhooks or moderation decisions."""
import argparse
import base64
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import subprocess
import time

VERSION = '0.1.3'


def roi(frame, box):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    return frame[round(y1*h):round(y2*h), round(x1*w):round(x2*w)]


def load_engine(args):
    if args.backend == 'reviewbot':
        source = args.reviewbot_root/'auto'/'ocr.py'
        if not source.is_file():
            raise ValueError('Set --reviewbot-root to the folder containing auto/ocr.py, or use --backend rapidocr')
        spec = importlib.util.spec_from_file_location('damage_ocr', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.OCR(args.model)
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR(use_angle_cls=False, det_limit_type='max', det_limit_side_len=960,
                      intra_op_num_threads=2, inter_op_num_threads=1)
    def read(image, scale=1):
        import cv2
        if scale != 1:
            image = cv2.resize(image, None, fx=scale, fy=scale)
        found, _ = engine(image)
        boxes = []
        for points, text, confidence in found or []:
            xs = [p[0]/scale for p in points]; ys = [p[1]/scale for p in points]
            boxes.append((min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys), text, float(confidence)))
        return boxes
    return read


def numeric_read(boxes, confidence=.75):
    candidates = []
    for x, y, w, h, text, score in boxes:
        text = text.strip()
        if score < confidence or not re.fullmatch(r'[0-9][0-9, .]*', text):
            continue
        digits = re.sub(r'\D', '', text)
        if digits and len(digits) <= 12:
            candidates.append((w*h, score, int(digits)))
    return max(candidates)[2] if candidates else None


class Stable:
    def __init__(self, count):
        self.count = count
        self.candidate = object()
        self.n = 0
    def push(self, value):
        if value == self.candidate:
            self.n += 1
        else:
            self.candidate, self.n = value, 1
        return self.n >= self.count


class Tracker:
    """The displayed owner is deliberately independent from the current actor."""
    def __init__(self, stable_frames=2):
        self.actor_filter = Stable(stable_frames)
        self.damage_filter = Stable(stable_frames)
        self.actor = None
        self.pending_actor = None
        self.current = None
        self.events = []
        self.blank = False
        self.number_seen = False
        self.last_value = None
        self.faction = None
        self.action_id = 0
        self.actions = []
        self.last_confirmed_state = None

    def finish_event(self, reason):
        if self.current is not None:
            self.current['closed_by'] = reason
            self.events.append(self.current)
            self.current = None

    def push(self, t, actor, value, panel_present, faction='ally'):
        state = (actor if faction == 'ally' else None, faction)
        if self.actor_filter.push(state) and state != (self.actor, self.faction):
            self.actor, self.faction = state
            confirmed = self.faction == 'enemy' or self.actor is not None
            new_action = confirmed and state != self.last_confirmed_state
            if new_action:
                self.action_id += 1
                self.last_confirmed_state = state
            if self.faction != 'unknown':
                self.pending_actor = self.actor
            if self.actor is not None and new_action:
                self.actions.append({'action_id': self.action_id, 'actor': self.actor,
                                     'observed_at': t, 'damage_observed': False})
        if not panel_present:
            if self.damage_filter.push('absent'):
                self.finish_event('panel_absent')
                self.blank = True
                self.last_value = None
            return
        if value is None:
            self.damage_filter.push('unreadable')
            return
        if not self.damage_filter.push(value):
            return
        changed = value != self.last_value
        self.last_value = value
        self.number_seen = True
        # Keep old lingering totals, but do not assign a replacement during a
        # confirmed enemy turn to an ally. Unknown marker evidence stays unknown.
        if self.faction == 'enemy':
            if changed:
                self.finish_event('number_changed_during_enemy_turn')
            return
        handover = (self.current is not None and self.pending_actor is not None
                    and self.action_id != self.current.get('action_id') and changed)
        if changed and self.actor is None and self.faction == 'ally' and self.current is not None:
            self.finish_event('number_changed_with_unknown_actor')
        if handover:
            self.finish_event('actor_handover_and_number_change')
        if self.current is None:
            if not changed and not self.blank:
                return
            owner = self.pending_actor or self.actor
            self.current = {'id': len(self.events)+1, 'actor': owner,
                            'action_id': self.action_id if owner else None, 'start': t,
                            'last_read': t, 'damage': value, 'stable_updates': 1,
                            'evidence_t': t, 'reading_warnings': [],
                            'attribution': 'pending_actor_on_number_change' if handover else 'visible_actor',
                            'needs_review': True}
            if owner is None:
                self.current['attribution'] = 'unattributed'
            for action in self.actions:
                if action['action_id'] == self.current['action_id']:
                    action['damage_observed'] = True
            self.pending_actor = None
            self.blank = False
        else:
            if value < self.current['damage']:
                self.current['reading_warnings'].append({'t': t, 'kind': 'decrease_without_confirmed_handover',
                                                         'previous': self.current['damage'], 'value': value})
            self.current.update(last_read=t, damage=value, evidence_t=t)
            self.current['stable_updates'] += 1


def scan(args):
    import cv2
    import numpy as np
    profile = json.loads(args.profile.read_text(encoding='utf-8-sig'))
    for name in ('actor_roi', 'damage_roi') + (('marker_roi',) if 'marker_roi' in profile else ()):
        box = profile[name]
        if (len(box) != 4 or not all(type(x) in (int, float) and math.isfinite(x) for x in box)
                or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1):
            raise ValueError(f'Invalid normalized {name}')
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Choose an empty output directory to avoid mixing runs')
    args.output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    rate = cap.get(cv2.CAP_PROP_FPS); total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if not cap.isOpened() or rate <= 0 or total <= 0:
        cap.release(); raise ValueError('Could not probe video')
    probe = subprocess.run([args.ffprobe, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=duration:format=duration", "-of", "json", str(args.video)],
                           capture_output=True, text=True, check=True)
    metadata = json.loads(probe.stdout)
    duration = float(metadata["streams"][0].get("duration") or metadata["format"]["duration"])
    end = min(duration, args.end if args.end is not None else duration)
    if end <= args.start:
        cap.release(); raise ValueError('Empty scan interval')
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH); height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if abs(width/height-profile.get('aspect_ratio', width/height)) > .03:
        cap.release(); raise ValueError('Video aspect ratio differs from profile; calibrate its ROIs first')
    asset_matcher = None
    templates = {}
    if 'catalog' in profile:
        from portraits import AssetMatcher
        asset_matcher = AssetMatcher(args.profile, profile, args.team, width)
        templates = asset_matcher.owners
    else:
        for actor, data in profile['portraits'].items():
            if isinstance(data, dict) and 'file' in data:
                template = cv2.imread(str(args.profile.parent/data['file']))
            else:
                template = cv2.imdecode(np.frombuffer(base64.b64decode(data), np.uint8), 1)
            if template is None:
                raise ValueError(f'Invalid portrait image for {actor}')
            templates[actor] = cv2.resize(template, (96, 56))
    if not templates:
        cap.release(); raise ValueError('Profile has no portraits')
    engine = load_engine(args)
    tracker = Tracker(args.stable_frames)
    started = time.perf_counter()
    # Sequential decode avoids a separate seek for every sampled frame.
    cap.set(cv2.CAP_PROP_POS_MSEC, args.start*1000)
    next_sample = args.start
    index = round(args.start*rate)
    sampled = ocr_calls = 0
    next_progress = args.start
    evidence = args.output/'evidence'; evidence.mkdir(exist_ok=True)
    raw = (args.output/'damage_readings.jsonl').open('w', encoding='utf8', buffering=1)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC)/1000; index += 1
            if t >= end:
                break
            if t+1e-7 < next_sample:
                continue
            next_sample += 1/args.fps
            sampled += 1
            faction = 'ally'
            marker_evidence = None
            if 'marker_roi' in profile:
                from faction import classify_marker
                marker = roi(frame, profile['marker_roi'])
                faction, marker_evidence = classify_marker(marker,
                    min_pixels=max(2, round(profile.get('marker_min_pixels', 5)*width*height/(1920*1080))))
            portrait = roi(frame, profile['actor_roi'])
            variant = None
            if faction != 'ally':
                actor, scores, variant = None, [], None
            elif asset_matcher:
                actor, scores, variant = asset_matcher.match(portrait)
            else:
                portrait = cv2.resize(portrait, (96, 56))
                scores = sorted(((float(cv2.matchTemplate(portrait, tpl, cv2.TM_CCOEFF_NORMED)[0, 0]), actor)
                                 for actor, tpl in templates.items()), reverse=True)
                actor = scores[0][1]
            best = scores[0][0] if scores else -1
            margin = best-scores[1][0] if len(scores)>1 else best
            if best < profile.get('portrait_threshold', .65) or margin < profile.get('portrait_margin', .06):
                actor = None
            damage = roi(frame, profile['damage_roi'])
            # Yellow number presence, distinct from recognition success.
            hsv = cv2.cvtColor(damage, cv2.COLOR_BGR2HSV)
            mask = ((hsv[..., 0] >= 15) & (hsv[..., 0] <= 45)
                    & (hsv[..., 1] > 55) & (hsv[..., 2] > 150)).astype(np.uint8)
            panel_present = float(mask.mean()) >= profile.get('damage_pixel_fraction', .007)
            boxes = engine(damage, scale=2) if panel_present else []
            ocr_calls += bool(panel_present)
            value = numeric_read(boxes, args.ocr_confidence)
            tracker.push(round(t, 4), actor, value, panel_present, faction)
            row = {'t': round(t, 4), 'actor': actor, 'faction': faction, 'marker_evidence': marker_evidence,
                   'portrait_variant': variant, 'actor_scores': {name: round(score, 4) for score, name in scores},
                   'damage': value, 'panel_present': panel_present,
                   'ocr': [{'text': b[4], 'confidence': round(b[5], 4)} for b in boxes],
                   'display_owner': tracker.current['actor'] if tracker.current else None,
                   'pending_actor': tracker.pending_actor}
            raw.write(json.dumps(row, ensure_ascii=False)+'\n')
            # Save only when the accepted evidence timestamp changes.
            if tracker.current and tracker.current['evidence_t'] == round(t, 4):
                cv2.imwrite(str(evidence/f"event_{tracker.current['id']:04d}_damage.jpg"), damage)
                cv2.imwrite(str(evidence/f"event_{tracker.current['id']:04d}_actor.jpg"), portrait)
            if t >= next_progress:
                print(f'{t:.2f}/{end:.2f}s | {len(tracker.events)} closed events | actor={actor} damage={value}', flush=True)
                next_progress = t+10
    finally:
        cap.release(); raw.close()
    if next_sample < end-1/args.fps:
        raise RuntimeError('Video decoding ended early; raw diagnostics retained, no final summary written')
    tracker.finish_event('interval_end')
    totals = dict.fromkeys(templates, 0)
    unknown = 0
    with (args.output/'damage_events.jsonl').open('w', encoding='utf8') as f:
        for event in tracker.events:
            if event['actor'] in totals:
                totals[event['actor']] += event['damage']
            else:
                unknown += event['damage']
            f.write(json.dumps(event, ensure_ascii=False)+'\n')
    with (args.output/'action_observations.jsonl').open('w', encoding='utf8') as f:
        for action in tracker.actions:
            action['status'] = 'damage_observed' if action['damage_observed'] else 'no_damage_assigned'
            f.write(json.dumps(action, ensure_ascii=False)+'\n')
    total_damage = sum(totals.values())+unknown
    rows = [{'character': actor, 'damage': value,
             'share_of_detected_damage': value/total_damage if total_damage else None}
            for actor, value in totals.items()]
    summary = {'version': VERSION, 'status': 'EXPERIMENTAL_REVIEW_REQUIRED',
               'video': str(args.video), 'range': [args.start, end],
               'profile_sha256': hashlib.sha256(args.profile.read_bytes()).hexdigest(),
               'team': args.team,
               'catalog_sha256': hashlib.sha256((args.profile.parent/profile['catalog']).read_bytes()).hexdigest() if 'catalog' in profile else None,
               'characters': rows, 'unattributed_damage': unknown, 'detected_damage_total': total_damage,
               'event_count': len(tracker.events), 'performance': {'sampled_frames': sampled,
               'ocr_calls': ocr_calls, 'elapsed_seconds': round(time.perf_counter()-started, 3)},
               'limitations': ['Shares concern detected action-panel totals, not independently verified true damage.',
                   'Portrait handover plus a changed number is provisional ownership evidence.',
                   'DoT, summons, assists, queued ultimates and identical consecutive totals are not resolved.',
                   'Same-character consecutive actions without panel disappearance may merge.',
                   'Stable OCR errors or missed panel boundaries can distort totals.',
                   'Clip/interval boundaries can truncate the first or last action.',
                   'No completeness percentage can be established from these detections alone.']}
    pending = args.output/'damage_summary.pending'
    pending.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    pending.replace(args.output/'damage_summary.json')
    with (args.output/'damage_summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['character','damage','share_of_detected_damage'])
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--profile', type=Path, default=Path(__file__).with_name('asset_profile.json'))
    p.add_argument('--output', type=Path, default=Path('work')/('damage_'+time.strftime('%Y%m%d_%H%M%S')))
    p.add_argument('--start', type=float, default=0)
    p.add_argument('--end', type=float)
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--fps', type=float, default=12)
    p.add_argument('--stable-frames', type=int, default=2)
    p.add_argument('--ocr-confidence', type=float, default=.75)
    p.add_argument('--backend', choices=['reviewbot','rapidocr'], default='rapidocr')
    p.add_argument('--team', nargs='+', default=[], help='Character IDs or quoted names for asset profile')
    p.add_argument('--model', default='latin')
    p.add_argument('--reviewbot-root', type=Path, default=Path(__file__).resolve().parent.parent)
    a = p.parse_args()
    if (not math.isfinite(a.fps) or not 0<a.fps<=120 or a.stable_frames<2
            or not math.isfinite(a.start) or a.start<0 or not 0<=a.ocr_confidence<=1
            or (a.end is not None and (not math.isfinite(a.end) or a.end<=a.start))):
        p.error('Invalid interval, fps, confidence or stable-frame settings')
    if not a.video.is_file() or not a.profile.is_file():
        p.error('Video and profile files must exist')
    a.video=a.video.resolve(); a.reviewbot_root=a.reviewbot_root.resolve()
    try:
        scan(a)
    except (ValueError, RuntimeError, ImportError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()
