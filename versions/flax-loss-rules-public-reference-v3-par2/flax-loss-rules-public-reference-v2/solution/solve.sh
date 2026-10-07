#!/bin/bash
set -euo pipefail
cd /workspace
rm -rf -- /workspace/candidate
mkdir /workspace/candidate
cp -- /opt/flax-assets/reference-v2/loss.py /workspace/candidate/loss.py
cp -- /opt/flax-assets/reference-v2/relaxation_rules.json /workspace/candidate/relaxation_rules.json
cp -- /opt/flax-assets/reference-v2/complementary_rules.json /workspace/candidate/complementary_rules.json
cp -- /opt/flax-assets/reference-v2/manifest.json /workspace/candidate/manifest.json
