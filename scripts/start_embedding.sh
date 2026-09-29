#!/usr/bin/env bash
# 用 vLLM 启动 Qwen3-Embedding-8B 的 AWQ-INT4 量化版本，对外提供
# OpenAI 兼容的 /v1/embeddings 接口（默认端口 8001）。
#
# 适用环境：WSL2 / Linux + NVIDIA GPU（RTX 4060 8GB 可运行）。
# Windows 原生不支持 vLLM，请在 WSL2 Ubuntu 中执行本脚本。
#
# 用法：
#   bash scripts/start_embedding.sh
#
# 可用环境变量覆盖默认值：
#   EMBED_MODEL         模型仓库/本地路径
#   EMBED_PORT          服务端口（默认 8001）
#   MAX_MODEL_LEN       最大上下文长度（默认 8192，越大越占显存/KV cache）
#   GPU_MEM_UTIL        显存占用比例（默认 0.90）
#   ENFORCE_EAGER       1=关闭 CUDA Graph 省显存（默认 1）；0=开启，吞吐更高
#   HF_ENDPOINT         HuggingFace 镜像，国内可设 https://hf-mirror.com

set -euo pipefail

EMBED_MODEL="${EMBED_MODEL:-Qwen/Qwen3-Embedding-8B-AWQ-INT4}"
EMBED_PORT="${EMBED_PORT:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.90}"
ENFORCE_EAGER="${ENFORCE_EAGER:-1}"

# 国内网络默认走 HF 镜像；不需要时在外部显式 export HF_ENDPOINT= 即可
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# 前置检查：vllm 是否安装
if ! command -v vllm >/dev/null 2>&1; then
    cat >&2 <<'EOF'
[错误] 找不到 vllm。请先安装（建议在独立虚拟环境中）：
    pip install vllm
若使用 uv：
    uv pip install vllm
EOF
    exit 1
fi

# 前置检查：GPU 是否可见
if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "[警告] 找不到 nvidia-smi，请确认已安装 NVIDIA 驱动且在 WSL2 中能访问 GPU。" >&2
fi

# 组装可选参数
EXTRA_ARGS=()
if [[ "${ENFORCE_EAGER}" == "1" ]]; then
    EXTRA_ARGS+=("--enforce-eager")
fi

echo "============================================================"
echo " 模型      : ${EMBED_MODEL}"
echo " 端口      : ${EMBED_PORT}  (POST http://localhost:${EMBED_PORT}/v1/embeddings)"
echo " 最大长度  : ${MAX_MODEL_LEN}"
echo " 显存比例  : ${GPU_MEM_UTIL}"
echo " Eager 模式: ${ENFORCE_EAGER}"
echo " HF 镜像   : ${HF_ENDPOINT}"
echo "============================================================"

# --quantization awq：权重为 AWQ-INT4 时显式声明（新版 vllm 多可自动识别，
# 显式指定可避免个别版本检测失败）。
# --dtype float16：4060 上的稳定选择；AWQ 内核要求 fp16。
exec vllm serve "${EMBED_MODEL}" \
    --port "${EMBED_PORT}" \
    --dtype float16 \
    --quantization awq \
    --max-model-len "${MAX_MODEL_LEN}" \
    --gpu-memory-utilization "${GPU_MEM_UTIL}" \
    --trust-remote-code \
    "${EXTRA_ARGS[@]}"
