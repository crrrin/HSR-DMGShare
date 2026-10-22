"""Masked asset matching in the active portrait region; labels aggregate to owners."""
import json
from pathlib import Path
import cv2
import numpy as np

class AssetMatcher:
    def __init__(self, profile_path, profile, team, width):
        path=profile_path.parent/profile['catalog']
        entries=json.loads(path.read_text(encoding='utf8'))['entries']
        selected=set(team)
        self.entries=[e for e in entries if e['detect_actor'] and (e['character_id'] in selected or e['character'] in selected)]
        known={e['character'] for e in self.entries}|{e['character_id'] for e in self.entries}
        if selected-known: raise ValueError('Unknown team members: '+', '.join(sorted(selected-known)))
        if not self.entries: raise ValueError('Specify --team with character names or IDs')
        self.owners={e['character']:0 for e in self.entries}
        self.templates=[]
        for e in self.entries:
            image=cv2.imread(str(path.parent/e['file']),cv2.IMREAD_UNCHANGED)
            if image is None or image.shape[2]!=4: raise ValueError('Expected RGBA portrait: '+e['file'])
            for size in profile.get('portrait_widths_at_1920',[110,120,130,140]):
                w=round(size*width/1920);h=round(w*image.shape[0]/image.shape[1])
                resized=cv2.resize(image,(w,h))
                mask=(resized[:,:,3]>240).astype(np.uint8)*255
                self.templates.append((e,resized[:,:,:3],mask))
    def match(self,crop):
        owner_scores={};winner={}
        for e,tpl,mask in self.templates:
            if tpl.shape[0]>crop.shape[0] or tpl.shape[1]>crop.shape[1]:continue
            scoremap=cv2.matchTemplate(crop,tpl,cv2.TM_CCORR_NORMED,mask=mask)
            score=float(np.nan_to_num(scoremap,nan=-1,posinf=-1,neginf=-1).max())
            owner=e['character']
            if score>owner_scores.get(owner,-1):owner_scores[owner]=score;winner[owner]=e['id']
        scores=sorted(((v,k) for k,v in owner_scores.items()),reverse=True)
        if not scores:return None,[],None
        return scores[0][1],scores,winner[scores[0][1]]
