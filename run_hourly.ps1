# 每小时流水线启动器（供 Windows 计划任务调用）
$ErrorActionPreference = "Continue"
$py = "F:\F03_Deps_Hub\Python_Local\bin\python.exe"
$script = "F:\F05_Projects_Hub\智能网文小说创作工作台\hourly_pipeline.py"
$logDir = "F:\F05_Projects_Hub\穿越之我是杨广\_工单与报告\hourly_log"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$out = Join-Path $logDir "sched_$stamp.log"
& $py $script *>&1 | Out-File -FilePath $out -Encoding utf8
exit 0
