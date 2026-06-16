#!/bin/zsh
# 华世王镞 V2 环境自检脚本
# 用法: zsh backend/scripts/maintenance/environment_check.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass_count=0
fail_count=0

check_pass() {
  echo -e "${GREEN}[通过]${NC} $1"
  ((pass_count++))
}

check_fail() {
  echo -e "${RED}[失败]${NC} $1"
  ((fail_count++))
}

BACKEND_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$BACKEND_ROOT"

# 1 Python 版本 >= 3.14
echo "━━━ 1/5 Python 版本检查 ━━━"
if command -v python3 &>/dev/null; then
  ver=$(python3 --version 2>&1 | awk '{print $2}')
  major=$(echo "$ver" | cut -d. -f1)
  minor=$(echo "$ver" | cut -d. -f2)
  if [[ "$major" -gt 3 || ("$major" -eq 3 && "$minor" -ge 14) ]]; then
    check_pass "Python $ver >= 3.14"
  else
    check_fail "Python $ver < 3.14，需要 Python 3.14+"
  fi
else
  check_fail "未找到 python3 命令"
fi

# 2 PostgreSQL 连接检查
echo "━━━ 2/5 PostgreSQL 连接检查 ━━━"
python3 << 'PYEOF' 2>&1
import asyncio, sys
sys.path.insert(0, '.')
try:
    import asyncpg
except ImportError:
    print("FAIL:asyncpg 未安装，请先执行 pip install -r requirements.txt")
    sys.exit(1)
from app.config import get_settings

async def check():
    settings = get_settings()
    try:
        conn = await asyncpg.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
        )
        await conn.close()
        print("OK")
    except Exception as e:
        print(f"FAIL:{e}")

asyncio.run(check())
PYEOF
if [[ $? -eq 0 ]]; then
  check_pass "PostgreSQL 连接正常"
else
  check_fail "PostgreSQL 连接失败"
fi

# 3 pgvector 扩展检查
echo "━━━ 3/5 pgvector 扩展检查 ━━━"
python3 << 'PYEOF' 2>&1
import asyncio, sys
sys.path.insert(0, '.')
try:
    import asyncpg
except ImportError:
    print("FAIL:asyncpg 未安装")
    sys.exit(1)
from app.config import get_settings

async def check():
    settings = get_settings()
    try:
        conn = await asyncpg.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
        )
        row = await conn.fetchrow("SELECT 1 FROM pg_extension WHERE extname='vector'")
        await conn.close()
        if row:
            print("OK")
        else:
            print("FAIL:pgvector 扩展未创建，请执行: CREATE EXTENSION vector;")
    except Exception as e:
        print(f"FAIL:{e}")

asyncio.run(check())
PYEOF
if [[ $? -eq 0 ]]; then
  check_pass "pgvector 扩展已安装"
else
  check_fail "pgvector 扩展检查失败"
fi

# 4 Ollama 服务可达检查
echo "━━━ 4/5 Ollama 嵌入服务检查 ━━━"
if command -v curl &>/dev/null; then
  curl -s -o /dev/null --connect-timeout 5 http://127.0.0.1:11434 2>/dev/null
  if [[ $? -eq 0 ]]; then
    check_pass "Ollama 服务可达 (127.0.0.1:11434)"
  else
    check_fail "Ollama 服务不可达 (127.0.0.1:11434)，请确认 Ollama 已启动"
  fi
else
  check_fail "未找到 curl 命令"
fi

# 5 pip check
echo "━━━ 5/5 pip 依赖检查 ━━━"
if command -v pip3 &>/dev/null; then
  pip3 check 2>&1
  if [[ $? -eq 0 ]]; then
    check_pass "pip check 通过，所有依赖已安装"
  else
    check_fail "pip check 失败，请执行 pip install -r requirements.txt"
  fi
else
  check_fail "未找到 pip3 命令"
fi

echo ""
echo "═══════════════════════════"
echo "结果: $pass_count 通过, $fail_count 失败"
echo "═══════════════════════════"

if [[ $fail_count -gt 0 ]]; then
  exit 1
fi
