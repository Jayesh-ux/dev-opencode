#!/bin/bash
export GEMINI_API_KEY="AIzaSyAApKyoZndYwv2qPeB_B85qOnt1QRpAO8I"
cd /root/dev/backend
/data/data/com.termux/files/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning < /dev/null > /tmp/backend.log 2>&1
