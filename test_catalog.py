import json
from pathlib import Path
import unittest

class CatalogTests(unittest.TestCase):
    def test_catalog_files_and_ownership(self):
        root=Path(__file__).parent
        entries=json.loads((root/'catalog.json').read_text(encoding='utf8'))['entries']
        self.assertEqual(len(entries),129)
        self.assertEqual(len({e['id'] for e in entries}),129)
        for e in entries:self.assertTrue((root/e['file']).is_file(),e['id'])
        indexed={e['id']:e for e in entries}
        self.assertFalse(indexed['1404B_Active_Bg']['detect_actor'])
        self.assertEqual(indexed['1131001']['character_id'],'1310')
        self.assertEqual(indexed['1510_BE']['character_id'],'1510')
        self.assertNotIn('1408B_02',indexed)
        self.assertNotIn('1404B_Active',indexed)
