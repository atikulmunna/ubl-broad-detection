#!/bin/bash
docker logs -f ai-server 2>&1 | grep "^{" | jq -r '.message'

# when testing with main.py
# python main.py 2>&1 | jq -r '.message' 