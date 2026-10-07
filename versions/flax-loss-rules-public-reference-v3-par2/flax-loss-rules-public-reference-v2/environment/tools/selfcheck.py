"""Read-only public manifest/digest/static-rule/loss-syntax check."""
import argparse
import json
from admission import admit, CandidateInvalid

parser = argparse.ArgumentParser()
parser.add_argument('--json', action='store_true', help='Emit machine-readable diagnostics (also the default).')
parser.parse_args()
try:
    manifest, blobs, hashes = admit()
    print(json.dumps({'status': 'admitted_static', 'candidate_id': manifest['candidate_id'], 'components': hashes,
                      'scope': 'manifest, paths, bytes, static rules, loss syntax; no runtime or scoring claim'}))
except CandidateInvalid as exc:
    print(json.dumps({'status': 'candidate_invalid', 'errors': [exc.error]}))
    raise SystemExit(1)
