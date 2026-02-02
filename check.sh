#!/bin/bash
# Build validation script - runs all checks before committing

set -e  # Exit on first error

echo "🔍 Running build validation checks..."
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Track failures
FAILURES=0

# 1. Type checking with mypy
echo "📝 Running type checking (mypy)..."
if uv run mypy debate/ --pretty; then
    echo -e "${GREEN}✓ Type checking passed${NC}"
else
    echo -e "${RED}✗ Type checking failed${NC}"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 2. Linting with ruff
echo "🔧 Running linter (ruff)..."
if uv run ruff check debate/; then
    echo -e "${GREEN}✓ Linting passed${NC}"
else
    echo -e "${RED}✗ Linting failed${NC}"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 3. Format checking with ruff
echo "🎨 Checking code formatting (ruff format)..."
if uv run ruff format --check debate/; then
    echo -e "${GREEN}✓ Formatting check passed${NC}"
else
    echo -e "${RED}✗ Formatting check failed${NC}"
    echo "Run 'uv run ruff format debate/' to fix"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 4. Python syntax check
echo "🐍 Checking Python syntax..."
if python3 -m py_compile debate/*.py; then
    echo -e "${GREEN}✓ Syntax check passed${NC}"
else
    echo -e "${RED}✗ Syntax check failed${NC}"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 5. Run tests if they exist
if [ -d "tests" ] && [ -n "$(ls -A tests/*.py 2>/dev/null)" ]; then
    echo "🧪 Running tests (pytest)..."
    if uv run pytest tests/ -v; then
        echo -e "${GREEN}✓ Tests passed${NC}"
    else
        echo -e "${RED}✗ Tests failed${NC}"
        FAILURES=$((FAILURES + 1))
    fi
    echo ""
fi

# Summary
echo "════════════════════════════════════════"
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo "Safe to commit."
    exit 0
else
    echo -e "${RED}✗ $FAILURES check(s) failed${NC}"
    echo "Please fix the issues before committing."
    exit 1
fi
