#!/bin/bash
exec 2>error_log_wps_run.txt

# 환경 변수 설정
export $(grep -v '^#' .env | xargs)

# 환경 변수 확인 (디버깅용)
echo "Current Environment: $ENV"
echo "HOME directory: $HOME"

# wps 실행하기