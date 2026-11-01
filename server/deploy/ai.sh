#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – the local AI on this server (EML-040, EML-044).
#
#   sudo rentalars ai install [--model NAME|FILE.gguf] [--sha256 HASH] [--port N] [--threads N] [--keep-model] [--rebuild] [--dry-run]
#   sudo rentalars ai remove [--keep-model] [--dry-run]
#   sudo rentalars ai register --url http://127.0.0.1:PORT/v1 --model NAME [--context N]
#   sudo rentalars ai status
#   sudo rentalars ai refresh [--dry-run]       (run by every update by itself)
#
# "install" puts a small language model on this server, for the summaries of
# the correspondence – so that mails do not leave the server and nothing is
# paid per use:
#
#   1. checks the system (Ubuntu 24.04/26.04, Raspberry Pi OS on Debian 13;
#      64 bit), the memory and the free space;
#   2. checks the processor: on x86-64 the model needs AVX2 and FMA to
#      be fast; a virtual machine often hides them (Proxmox: processor type
#      "host" helps) – the command says so;
#   3. chooses the model by memory, cores and processor: "Qwen3 4B"
#      only with 6 GB of memory, four physical cores and AVX2/FMA (or a 64-bit
#      ARM server that is not a Raspberry Pi), otherwise "Qwen3 1.7B" – both
#      from Qwen (Alibaba Cloud), licence Apache 2.0, which allows commercial
#      use, quantised to Q4_K_M (GGUF); "--model qwen3-1.7b|qwen3-4b|qwen2.5-1.5b"
#      chooses one (also to change the model of an installed local AI), and
#      "--model FILE.gguf" takes a file already on the server (no internet);
#   4. installs llama.cpp's "llama-server": where the distribution has it
#      (Ubuntu 26.04: package llama.cpp-tools), from there; otherwise
#      (Ubuntu 24.04, Raspberry Pi OS 13) it builds the release b8681 from
#      its source with cmake and checks that the source is exactly that
#      release (the git commit below) – on a Raspberry Pi that takes
#      15 to 40 minutes; a server built before is kept;
#   5. downloads the model and checks its SHA-256 checksum; a model used
#      before is deleted once the new one runs (unless --keep-model);
#   6. runs it as the service "rentalars-ai" (deploy/systemd/rentalars-ai.service):
#      bound to 127.0.0.1, with its own user without rights, without network
#      except this machine, with lower priority (Nice) and a memory limit
#      (MemoryMax), with one thread per physical core (a second thread on a
#      core does not make it faster), and with thinking switched off
#      ("--reasoning off", "--reasoning-budget 0" where llama-server knows them);
#   7. writes where it listens into /etc/rentalars/ai-local.conf – Rentalars
#      reads the file at every use, nothing has to be restarted – and sends
#      a test prompt that measures reading and writing speed.
#
# The summaries are switched on in Rentalars afterwards: Einstellungen → KI.
# "register" tells Rentalars about an inference server the operator runs
# himself on this machine (Ollama, LM Studio); "remove" undoes "install" or
# "register". With "--dry-run" nothing is changed: the plan is shown – also
# without root.
#
# "refresh" takes over what a new version of Rentalars sets for the
# service – threads per physical core, thinking off, memory limit, the lines
# of ai-local.conf – and restarts the service only if something changed. It
# never downloads, builds or installs anything and never changes the model:
# a model is a large file, and llama-server comes from the Ubuntu package
# (updated with the system) or from a build that only "install --rebuild"
# makes again. It says when another model would suit this machine, when the
# processor lacks AVX2/FMA, and when a build lacks AVX2 the processor now
# has. "rentalars update" runs it after every successful update, and
# rentalars-ai-refresh.timer about a minute after every start of the server
# (so also after the update, whose update script does not know
# it yet, and after the processor type of a virtual machine was changed).
# It never fails its caller: a local AI that cannot be refreshed is warned
# about, and the update goes on.
#
# Root is needed only for this command; Rentalars itself never gets it.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

# --- What is installed where -----------------------------------------------------------------------
# RENTALARS_AI_TEST_ROOT puts every path below a folder and RENTALARS_AI_SYSTEMCTL replaces systemctl – only for
# the tests of "refresh" (tests/unit/test_084_ai.py); with them, root is not required.
readonly AI_TEST_ROOT="${RENTALARS_AI_TEST_ROOT:-}"
readonly AI_SYSTEMCTL="${RENTALARS_AI_SYSTEMCTL:-systemctl}"
readonly AI_HOME="${AI_TEST_ROOT}${AI_DIR}"
readonly AI_BIN="${AI_HOME}/bin/llama-server"
readonly AI_MODELS="${AI_HOME}/models"
readonly AI_SOURCE_DIR="${AI_HOME}/src"
# Packages this command installed itself, to remove them again with "remove".
readonly AI_PACKAGES_FILE="${AI_HOME}/${INSTALLED_PACKAGES_NAME}"
readonly AI_ENV_FILE="${AI_TEST_ROOT}${CONFIG_DIR}/ai-local.env"
AI_LOCAL_FILE="$(dirname "${CONFIG_FILE}")/ai-local.conf"
readonly AI_LOCAL_FILE
readonly AI_UNIT="rentalars-ai.service"
readonly AI_DROP_IN_DIR="${AI_TEST_ROOT}/etc/systemd/system/${AI_UNIT}.d"
readonly AI_DEFAULT_PORT=8093

# llama.cpp: the release that is built where the distribution has no package, and its commit.
readonly LLAMA_TAG="b8681"
readonly LLAMA_COMMIT="506200cf8b5c8419ce97d16dc8c50f4634e21ebe"
readonly LLAMA_REPOSITORY="https://github.com/ggml-org/llama.cpp.git"
readonly LLAMA_PACKAGE="llama.cpp-tools"

# The models: key, file, address, SHA-256, size in MB, name, licence, MemoryMax.
# Qwen3 1.7B (the conversion of the llama.cpp project, ggml-org) is the model for every server that is
# not clearly fast enough for Qwen3 4B; Qwen2.5 1.5B, the small model, can still be chosen.
readonly COMPACT_MODEL="qwen3-1.7b"
readonly SMALL_MODEL="qwen2.5-1.5b"
readonly LARGE_MODEL="qwen3-4b"
# Qwen3 4B only from this much memory (MB) and this many physical cores, and with AVX2/FMA; below
# SMALLEST_MEMORY_MB no model at all.
readonly LARGE_MODEL_FROM_MB=6000
readonly LARGE_MODEL_FROM_CORES=4
readonly SMALLEST_MEMORY_MB=1500
readonly MODEL_CONTEXT=8192

model_field() {
    local key="$1" field="$2"
    case "${key}:${field}" in
        "${COMPACT_MODEL}:file")    echo "Qwen3-1.7B-Q4_K_M.gguf" ;;
        "${COMPACT_MODEL}:url")     echo "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf" ;;
        "${COMPACT_MODEL}:sha256")  echo "d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5" ;;
        "${COMPACT_MODEL}:size_mb") echo 1223 ;;
        "${COMPACT_MODEL}:alias")   echo "qwen3-1.7b" ;;
        "${COMPACT_MODEL}:name")    echo "Qwen3 1.7B (Q4_K_M)" ;;
        "${COMPACT_MODEL}:memory")  echo "3G" ;;
        "${SMALL_MODEL}:file")    echo "qwen2.5-1.5b-instruct-q4_k_m.gguf" ;;
        "${SMALL_MODEL}:url")     echo "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf" ;;
        "${SMALL_MODEL}:sha256")  echo "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e" ;;
        "${SMALL_MODEL}:size_mb") echo 1066 ;;
        "${SMALL_MODEL}:alias")   echo "qwen2.5-1.5b-instruct" ;;
        "${SMALL_MODEL}:name")    echo "Qwen2.5 1.5B Instruct (Q4_K_M)" ;;
        "${SMALL_MODEL}:memory")  echo "2G" ;;
        "${LARGE_MODEL}:file")    echo "Qwen3-4B-Q4_K_M.gguf" ;;
        "${LARGE_MODEL}:url")     echo "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf" ;;
        "${LARGE_MODEL}:sha256")  echo "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5" ;;
        "${LARGE_MODEL}:size_mb") echo 2382 ;;
        "${LARGE_MODEL}:alias")   echo "qwen3-4b" ;;
        "${LARGE_MODEL}:name")    echo "Qwen3 4B (Q4_K_M)" ;;
        "${LARGE_MODEL}:memory")  echo "5G" ;;
        *:licence)                echo "Apache-2.0" ;;
        *) return 1 ;;
    esac
}

# The model for this server: choose_model MEMORY_MB PHYSICAL_CORES FAST -> key, or nothing below
# SMALLEST_MEMORY_MB. FAST is "yes" for a processor with the vector instructions the model needs
# (x86-64 with AVX2 and FMA, a 64-bit ARM server that is not a Raspberry Pi) – see fast_processor.
choose_model() {
    local memory="$1" cores="$2" fast="$3"
    if (( memory < SMALLEST_MEMORY_MB )); then
        return 0
    fi
    if (( memory >= LARGE_MODEL_FROM_MB && cores >= LARGE_MODEL_FROM_CORES )) && [[ "${fast}" == "yes" ]]; then
        echo "${LARGE_MODEL}"
    else
        echo "${COMPACT_MODEL}"
    fi
}

# Threads for the model: one per physical core – a second thread on the same core (hyper-threading) does not
# make it faster –, at least one, at most sixteen: model_threads PHYSICAL_CORES
model_threads() {
    local cores="$1"
    (( cores < 1 )) && cores=1
    (( cores > 16 )) && cores=16
    echo "${cores}"
}

# --- The processor -------------------------------------------------------------------------------
# The functions take the file they read (/proc/cpuinfo), so that tests can hand them made-up ones.

# The flags of the first processor (x86: "flags", ARM: "Features"): cpu_flags CPUINFO
cpu_flags() {
    awk -F': *' 'tolower($1) ~ /^(flags|features)[[:space:]]*$/ { print $2; exit }' "$1" 2> /dev/null || true
}

# The name of the processor: cpu_model CPUINFO
cpu_model() {
    awk -F': *' 'tolower($1) ~ /^model name[[:space:]]*$/ { print $2; exit }' "$1" 2> /dev/null || true
}

# Logical processors: logical_cpus CPUINFO
logical_cpus() {
    local count
    count="$(grep -c '^processor' "$1" 2> /dev/null || true)"
    echo "${count:-0}"
}

# Physical cores: the pairs of "physical id" and "core id"; without them (ARM, some virtual machines) every
# logical processor counts as one core: physical_cores CPUINFO
physical_cores() {
    local count
    count="$(awk -F': *' '
        tolower($1) ~ /^physical id/ { socket = $2 }
        tolower($1) ~ /^core id/     { cores[socket ":" $2] = 1 }
        END { n = 0; for (core in cores) n++; print n }' "$1" 2> /dev/null || echo 0)"
    if (( count < 1 )); then
        count="$(logical_cpus "$1")"
    fi
    echo "${count}"
}

# What an x86-64 processor lacks of what the model needs to be fast, e.g. "AVX2 FMA"; nothing on ARM or
# when all is there: missing_vectors CPUINFO ARCHITECTURE
missing_vectors() {
    local flags missing=()
    [[ "$2" == "amd64" || "$2" == "x86_64" ]] || return 0
    flags=" $(cpu_flags "$1") "
    [[ "${flags}" == "  " ]] && return 0
    [[ "${flags}" == *" avx2 "* ]] || missing+=(AVX2)
    [[ "${flags}" == *" fma "* ]] || missing+=(FMA)
    echo "${missing[*]}"
}

# Succeeds when the kernel says it runs in a virtual machine: in_virtual_machine CPUINFO
in_virtual_machine() {
    [[ " $(cpu_flags "$1") " == *" hypervisor "* ]]
}

# "yes" for a processor fast enough for Qwen3 4B: fast_processor CPUINFO ARCHITECTURE DEVICE_MODEL
fast_processor() {
    case "$2" in
        amd64|x86_64) [[ -z "$(missing_vectors "$1" "$2")" ]] && echo yes || echo no ;;
        arm64|aarch64) is_raspberry_pi "$3" && echo no || echo yes ;;
        *) echo no ;;
    esac
}

# Succeeds if nobody but root can change PATH: it and every folder above it belong to root, and nobody else
# may write to them (the group root aside). Links are followed – what is checked is what is used: root_only PATH
#
# Review: root runs llama-server ("--version", "--help") and writes the files of the service. Neither
# may rest on anything the service user, the user of the AI service or anybody else could have put there or
# swapped. With RENTALARS_AI_TEST_ROOT the check ends at that folder.
root_only() {
    local path top="/" owner group mode
    path="$(readlink -f -- "$1")" || return 1
    [[ -n "${path}" && -e "${path}" ]] || return 1
    if [[ -n "${AI_TEST_ROOT}" ]]; then
        top="$(readlink -f -- "${AI_TEST_ROOT}")"
    fi
    while :; do
        read -r owner group mode < <(stat -c '%u %g %a' -- "${path}") || return 1
        (( owner == 0 )) || return 1
        (( (8#${mode} & 8#002) == 0 )) || return 1
        (( (8#${mode} & 8#020) == 0 || group == 0 )) || return 1
        [[ "${path}" == "/" || "${path}" == "${top}" ]] && return 0
        path="$(dirname -- "${path}")"
    done
}

# The program a llama-server path stands for, if root may run it (see root_only); otherwise a warning and
# failure: trusted_binary BINARY
trusted_binary() {
    local real
    real="$(readlink -f -- "$1" 2> /dev/null || true)"
    if [[ -z "${real}" || ! -f "${real}" || ! -x "${real}" ]] || ! root_only "$(dirname -- "$1")" || ! root_only "${real}"; then
        warn "$(t "${1} wird nicht ausgeführt: das Programm oder ein Ordner darüber gehört nicht allein root. Prüfen: ls -l ${real:-$1}" "${1} is not run: the program or a folder above it does not belong to root alone. Check: ls -l ${real:-$1}")"
        return 1
    fi
    echo "${real}"
}

# The build number of an installed llama-server, e.g. 8681; nothing if unknown – or if root may not run it:
# llama_build BINARY
llama_build() {
    local binary
    [[ -x "$1" ]] || return 0
    binary="$(trusted_binary "$1" 2> /dev/null)" || return 0
    "${binary}" --version 2>&1 | sed -n 's/^version: *\([0-9][0-9]*\).*/\1/p' | head -n 1
}

# What a build of llama.cpp made on this processor can use (GGML_NATIVE): vector_flags CPUINFO ARCHITECTURE
# -> "avx2,fma", "avx2", "fma" or "none" on x86-64, "neon" on ARM.
vector_flags() {
    local flags found=()
    case "$2" in
        amd64|x86_64)
            flags=" $(cpu_flags "$1") "
            [[ "${flags}" == *" avx2 "* ]] && found+=(avx2)
            [[ "${flags}" == *" fma "* ]] && found+=(fma)
            if (( ${#found[@]} == 0 )); then
                echo none
            else
                local IFS=,
                echo "${found[*]}"
            fi ;;
        arm64|aarch64) echo neon ;;
        *) echo none ;;
    esac
}

# The options for llama-server beyond model, port, threads and context – those this llama-server knows:
# llama_extra_flags BINARY
#
# EML-040: no thinking first, for certain. llama.cpp 8681 (the Ubuntu 26.04 package and the release
# built here) knows "--reasoning off" – the switch that replaced "enable_thinking" on its command line – and
# "--reasoning-budget 0"; Rentalars sends "enable_thinking": false and "/no_think" as well. Every option is
# taken only if "--help" lists it, so that another llama-server (an older package, a version gone back to)
# still starts. Fails, without running it, if root may not run it (see trusted_binary).
llama_extra_flags() {
    local binary help_text extra=()
    binary="$(trusted_binary "$1")" || return 1
    help_text="$("${binary}" --help 2>&1 || true)"
    [[ "${help_text}" == *"--jinja"* ]] && extra+=(--jinja)
    [[ "${help_text}" == *"--no-webui"* ]] && extra+=(--no-webui)
    [[ "${help_text}" =~ --reasoning[[:space:]]+\[ ]] && extra+=(--reasoning off)
    [[ "${help_text}" == *"--reasoning-budget"* ]] && extra+=(--reasoning-budget 0)
    echo "${extra[*]}"
}

# The key of a model of the table by the name the server knows it by, or nothing: model_key_of ALIAS
model_key_of() {
    local key
    for key in "${COMPACT_MODEL}" "${SMALL_MODEL}" "${LARGE_MODEL}"; do
        if [[ "$(model_field "${key}" alias)" == "$1" ]]; then
            echo "${key}"
            return 0
        fi
    done
}

# One value of a KEY=VALUE file such as ai-local.env: env_value FILE KEY
env_value() {
    sed -n "s/^$2=//p" "$1" 2> /dev/null | tail -n 1
}

# One value of ai-local.conf: local_value KEY
local_value() {
    sed -n "s/^$1 = //p" "${AI_LOCAL_FILE}" 2> /dev/null | tail -n 1
}

# The two files the service reads – the options of llama-server and the limits of the unit:
#   write_service_files MODEL_FILE ALIAS PORT THREADS CONTEXT EXTRA MEMORY_MAX
write_service_files() {
    mkdir -p "$(dirname "${AI_ENV_FILE}")" "${AI_DROP_IN_DIR}"
    cat > "${AI_ENV_FILE}" <<EOF
# Written by "rentalars ai install" or "rentalars ai refresh" – read by ${AI_UNIT}.
AI_MODEL=$1
AI_ALIAS=$2
AI_PORT=$3
AI_THREADS=$4
AI_CONTEXT=$5
AI_EXTRA=$6
EOF
    chmod 644 "${AI_ENV_FILE}"
    cat > "${AI_DROP_IN_DIR}/50-limits.conf" <<EOF
# Written by "rentalars ai install" or "rentalars ai refresh": the memory of the model and its context, and the
# cores it may use.
[Service]
MemoryMax=$7
CPUQuota=$(( $4 * 100 ))%
EOF
    chmod 644 "${AI_DROP_IN_DIR}/50-limits.conf"
}

# Parallel compiler runs for the build: one per core and per GB of memory: build_jobs CORES MEMORY_MB
build_jobs() {
    local cores="$1" memory="$2" jobs
    jobs=$(( memory / 1024 ))
    (( jobs > cores )) && jobs="${cores}"
    (( jobs < 1 )) && jobs=1
    echo "${jobs}"
}

# Whether the distribution offers llama-server. RENTALARS_AI_PACKAGE=yes|no decides instead (the tests).
package_available() {
    case "${RENTALARS_AI_PACKAGE:-}" in
        yes) return 0 ;;
        no)  return 1 ;;
    esac
    command -v apt-cache > /dev/null || return 1
    local candidate
    candidate="$(apt-cache policy "${LLAMA_PACKAGE}" 2> /dev/null | sed -n 's/^ *Candidate: *//p')"
    [[ -n "${candidate}" && "${candidate}" != "(none)" ]]
}

# Succeeds for an address on this machine: http(s)://127.x.x.x, localhost or [::1], with port and path.
is_loopback_url() {
    [[ "$1" =~ ^https?://(127\.[0-9]+\.[0-9]+\.[0-9]+|localhost|\[::1\])(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$ ]]
}

# Succeeds for a model name as servers use them (qwen2.5:1.5b, Qwen/Qwen3-4B, model.gguf): is_model_name NAME
# Nothing else may reach ai-local.conf – a line break would add lines of its own.
is_model_name() {
    [[ "$1" =~ ^[A-Za-z0-9._:/-]{1,128}$ ]]
}

# Succeeds if something listens on this TCP port of the machine: port_in_use PORT
port_in_use() {
    command -v ss > /dev/null || return 1
    [[ -n "$(ss -ltnH "sport = :$1" 2> /dev/null)" ]]
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

# Write the file Rentalars reads (ai-local.conf):
#   write_local_file URL ALIAS NAME LICENCE CONTEXT THREADS SERVER KIND PHYSICAL_CORES BUILT_WITH
# KIND is "llama.cpp" (installed here) or "other" (registered); Rentalars switches thinking off
# accordingly (rentalars/ai/client.py). BUILT_WITH is what a build of llama-server could use of the
# processor it was made on ("avx2,fma", "none", "neon"), "package" for the Ubuntu package – which brings a
# variant for every processor and picks one at each start –, or "" when unknown.
write_local_file() {
    local temporary value
    for value in "$@"; do
        [[ "${value}" != *$'\n'* && "${value}" != *$'\r'* ]] || fail "$(t "Ein Wert enthält einen Zeilenumbruch." "A value contains a line break.")"
    done
    temporary="$(mktemp "${AI_LOCAL_FILE}.XXXXXX")"
    cat > "${temporary}" <<EOF
# Written by "rentalars ai install" or "rentalars ai register" on $(date -Iseconds).
# Rentalars reads it at every use of the local AI (EML-040); only an address on this machine counts.
# Removed by "rentalars ai remove".
[local_ai]
url = $1
model = $2
model_name = $3
model_licence = $4
context = $5
threads = $6
server = $7
server_kind = ${8:-llama.cpp}
physical_cores = ${9:-0}
built_with = ${10:-}
installed_at = $(date -Iseconds)
EOF
    chmod 644 "${temporary}"
    mv "${temporary}" "${AI_LOCAL_FILE}"
}

# Wait until the server answers: wait_for_server URL SECONDS
wait_for_server() {
    local url="$1" seconds="$2" waited=0
    until curl -fsS --max-time 5 "${url}/models" > /dev/null 2>&1; do
        (( waited >= seconds )) && return 1
        sleep 3
        waited=$(( waited + 3 ))
    done
}

# A test prompt; prints "SECONDS TOKENS_PER_SECOND": test_prompt URL ALIAS
test_prompt() {
    local url="$1" alias="$2" started answer seconds speed
    started="$(date +%s.%N)"
    answer="$(curl -fsS --max-time 600 -H 'Content-Type: application/json' "${url}/chat/completions" \
        -d "{\"model\": \"${alias}\", \"max_tokens\": 32, \"temperature\": 0, \"cache_prompt\": false, \"chat_template_kwargs\": {\"enable_thinking\": false}, \"messages\": [{\"role\": \"system\", \"content\": \"Du antwortest knapp. /no_think\"}, {\"role\": \"user\", \"content\": \"Nenne die vier Jahreszeiten, durch Kommas getrennt.\"}]}")" || return 1
    seconds="$(awk -v a="${started}" -v b="$(date +%s.%N)" 'BEGIN { printf "%.1f", b - a }')"
    # Reading (prompt) and writing speed apart, as llama-server reports them.
    speed="$(python3 -c 'import json, sys; t = json.load(sys.stdin).get("timings", {}); print(round(t.get("prompt_per_second", 0), 1), round(t.get("predicted_per_second", 0), 1))' <<<"${answer}" 2> /dev/null || echo "? ?")"
    echo "${seconds} ${speed}"
}

# The warning about missing vector instructions: warn_vectors MISSING IN_VM
warn_vectors() {
    [[ -n "$1" ]] || return 0
    warn "$(t "Der Prozessor meldet kein ${1// /, }: Die lokale KI läuft damit um ein Vielfaches langsamer." "The processor does not report ${1// /, }: the local AI runs several times slower without them.")"
    if [[ "$2" == "yes" ]]; then
        note "$(t 'In einer virtuellen Maschine: Prozessortyp auf „host“ stellen, z. B. in Proxmox unter Hardware → Prozessoren → Typ: host; danach die Maschine in Proxmox herunterfahren und wieder starten (ein Neustart von innen genügt nicht). Den Rest übernimmt Rentalars beim Start; muss ein selbst gebauter llama-server neu gebaut werden, sagt es das.' 'In a virtual machine: set the processor type to “host”, e.g. in Proxmox under Hardware → Processors → Type: host; then shut the machine down and start it again in Proxmox (a reboot from inside is not enough). Rentalars takes care of the rest at the start; should a llama-server built here need building again, it says so.')"
    fi
}

# --- The commands ---------------------------------------------------------------------------------------

usage() {
    sed -n '3,8p' "$(readlink -f "${BASH_SOURCE[0]}")" | sed 's/^# \{0,1\}//'
}

command="${1:-}"
shift || true
dry_run=false model_choice="" model_sha="" port="${AI_DEFAULT_PORT}" threads="" keep_model=false url="" context="${MODEL_CONTEXT}"
rebuild=false
while (( $# > 0 )); do
    case "$1" in
        --dry-run)    dry_run=true ;;
        --rebuild)    rebuild=true ;;
        --model)      model_choice="${2:?}"; shift ;;
        --sha256)     model_sha="${2:?}"; shift ;;
        --port)       port="${2:?}"; shift ;;
        --threads)    threads="${2:?}"; shift ;;
        --keep-model) keep_model=true ;;
        --url)        url="${2:?}"; shift ;;
        --context)    context="${2:?}"; shift ;;
        -h|--help)    usage; exit 0 ;;
        *) fail "$(t "Unbekannte Angabe: $1" "Unknown option: $1")" ;;
    esac
    shift
done
if ! [[ "${port}" =~ ^[0-9]{4,5}$ ]] || (( port < 1024 || port > 65535 )); then
    fail "$(t "--port braucht eine Zahl von 1024 bis 65535." "--port needs a number from 1024 to 65535.")"
fi
[[ -z "${threads}" || "${threads}" =~ ^[1-9][0-9]?$ ]] || fail "$(t "--threads braucht eine Zahl von 1 bis 99." "--threads needs a number from 1 to 99.")"
[[ "${context}" =~ ^[0-9]{4,7}$ ]] || fail "$(t "--context braucht eine Zahl von 1000 an." "--context needs a number from 1000 on.")"

do_install() {
    local os_release="${RENTALARS_AI_OS_RELEASE:-${OS_RELEASE_FILE}}" model_file="${RENTALARS_AI_DEVICE_MODEL:-${DEVICE_MODEL_FILE}}"
    local meminfo="${RENTALARS_AI_MEMINFO:-${MEMORY_INFO_FILE}}" architecture="${RENTALARS_AI_ARCH:-}"
    local cores="${RENTALARS_AI_CORES:-}" memory key="" file="" source_file="" sha size_mb name alias licence memory_max method
    local candidate server_label actual built_with=""
    # The processor – physical cores, AVX2/FMA, virtual machine (RENTALARS_AI_CPUINFO for the tests).
    local cpuinfo="${RENTALARS_AI_CPUINFO:-/proc/cpuinfo}" physical missing vm="no" fast
    [[ -n "${architecture}" ]] || architecture="$(dpkg --print-architecture 2> /dev/null || uname -m)"
    [[ -n "${cores}" ]] || cores="$(nproc 2> /dev/null || echo 1)"
    ${dry_run} || require_root
    check_system "${os_release}" "${model_file}" "${architecture}"
    memory="$(memory_mb "${meminfo}")"
    physical="$(physical_cores "${cpuinfo}")"
    (( physical > 0 )) || physical="${cores}"
    missing="$(missing_vectors "${cpuinfo}" "${architecture}")"
    in_virtual_machine "${cpuinfo}" && vm="yes"
    fast="$(fast_processor "${cpuinfo}" "${architecture}" "${SYSTEM_MODEL}")"
    [[ -n "${threads}" ]] || threads="$(model_threads "${physical}")"

    case "${model_choice}" in
        "") key="$(choose_model "${memory}" "${physical}" "${fast}")"
            [[ -n "${key}" ]] || fail "$(t "Für die lokale KI sind mindestens $((SMALLEST_MEMORY_MB / 1000 + 1)) GB Arbeitsspeicher nötig; hier sind es $(memory_text "${memory}")." "The local AI needs at least $((SMALLEST_MEMORY_MB / 1000 + 1)) GB of memory; this machine has $(memory_text "${memory}").")" ;;
        "${COMPACT_MODEL}"|"${SMALL_MODEL}"|"${LARGE_MODEL}") key="${model_choice}" ;;
        *.gguf)
            source_file="$(readlink -f "${model_choice}")"
            [[ -f "${source_file}" ]] || fail "$(t "${model_choice} gibt es nicht." "${model_choice} does not exist.")"
            for candidate in "${COMPACT_MODEL}" "${SMALL_MODEL}" "${LARGE_MODEL}"; do
                [[ "$(basename "${source_file}")" == "$(model_field "${candidate}" file)" ]] && key="${candidate}"
            done ;;
        *) fail "$(t "--model kennt ${COMPACT_MODEL}, ${LARGE_MODEL}, ${SMALL_MODEL} oder eine Datei *.gguf." "--model knows ${COMPACT_MODEL}, ${LARGE_MODEL}, ${SMALL_MODEL} or a file *.gguf.")" ;;
    esac
    if [[ -n "${key}" ]]; then
        file="$(model_field "${key}" file)" sha="$(model_field "${key}" sha256)" size_mb="$(model_field "${key}" size_mb)"
        name="$(model_field "${key}" name)" alias="$(model_field "${key}" alias)" licence="$(model_field "${key}" licence)"
        memory_max="$(model_field "${key}" memory)"
    else
        # An own model file: its checksum is the one given, else the one it has; licence unknown to us.
        file="$(basename "${source_file}")" sha="${model_sha}" size_mb=$(( $(stat -c %s "${source_file}") / 1048576 ))
        name="${file%.gguf}" alias="$(tr '[:upper:]' '[:lower:]' <<<"${file%.gguf}")" licence="$(t "siehe Modell" "see the model")"
        memory_max="$(( size_mb * 2 / 1024 + 2 ))G"
    fi
    if package_available; then method="package"; else method="build"; fi

    say "$(t "Lokale KI für Rentalars" "Local AI for Rentalars")"
    row 22 "$(t "System" "System")" "${SYSTEM_NAME:-?} (${SYSTEM_ARCHITECTURE})${SYSTEM_NOTE}"
    [[ -n "${SYSTEM_MODEL}" ]] && row 22 "$(t "Gerät" "Device")" "${SYSTEM_MODEL}"
    row 22 "$(t "Arbeitsspeicher" "Memory")" "$(memory_text "${memory}")"
    row 22 "$(t "Prozessor" "Processor")" "$(cpu_model "${cpuinfo}") – $(t "${physical} physische Kerne, $(logical_cpus "${cpuinfo}") logische" "${physical} physical cores, $(logical_cpus "${cpuinfo}") logical")$([[ "${vm}" == "yes" ]] && t ", virtuelle Maschine" ", virtual machine")"
    if [[ -n "${missing}" ]]; then
        row 22 "AVX2/FMA" "$(t "FEHLT: ${missing}" "MISSING: ${missing}")"
    elif [[ "${architecture}" == "amd64" || "${architecture}" == "x86_64" ]]; then
        row 22 "AVX2/FMA" "$(t "vorhanden" "present")"
    fi
    row 22 "$(t "Modell" "Model")" "${name} – $(t "Lizenz" "licence") ${licence}"
    if [[ -n "${source_file}" ]]; then
        row 22 "$(t "Modelldatei" "Model file")" "${source_file} → ${AI_MODELS}/${file}"
    else
        row 22 "$(t "Herunterladen" "Download")" "$(model_field "${key}" url) (${size_mb} MB)"
    fi
    row 22 "SHA-256" "${sha:-$(t "wird berechnet und angezeigt" "computed and shown")}"
    if [[ "${method}" == "package" ]]; then
        row 22 "llama-server" "$(t "Paket ${LLAMA_PACKAGE} der Distribution" "package ${LLAMA_PACKAGE} of the distribution")"
    else
        row 22 "llama-server" "$(t "aus dem Quelltext gebaut: llama.cpp ${LLAMA_TAG}, Commit ${LLAMA_COMMIT:0:12}, cmake mit $(build_jobs "${cores}" "${memory}") Prozessen" "built from source: llama.cpp ${LLAMA_TAG}, commit ${LLAMA_COMMIT:0:12}, cmake with $(build_jobs "${cores}" "${memory}") processes")"
    fi
    row 22 "$(t "Dienst" "Service")" "${AI_UNIT}: 127.0.0.1:${port}, --threads ${threads}, MemoryMax=${memory_max}, Nice=10"
    row 22 "Threads" "$(t "${threads} – einer je physischem Kern" "${threads} – one per physical core")"
    row 22 "$(t "Für Rentalars" "For Rentalars")" "${AI_LOCAL_FILE}"
    warn_vectors "${missing}" "${vm}"
    port_in_use "${port}" && ! systemctl is-active --quiet "${AI_UNIT}" 2> /dev/null \
        && fail "$(t "Port ${port} ist schon belegt. Wähle einen anderen mit --port." "Port ${port} is taken. Choose another one with --port.")"
    if ${dry_run}; then
        note ""
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    [[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"
    [[ -e "${APP_DIR}/deploy/systemd/${AI_UNIT}" ]] || fail "$(t "Die installierte Version von Rentalars kennt die lokale KI nicht." "The installed version of Rentalars does not know the local AI.")"
    # Root builds, downloads and runs here: only in folders nobody else can change.
    local folder
    root_only "$(dirname "${AI_HOME}")" \
        || fail "$(t "$(dirname "${AI_HOME}") gehört nicht allein root. Abgebrochen – prüfen: ls -ld $(dirname "${AI_HOME}")" "$(dirname "${AI_HOME}") does not belong to root alone. Stopped – check: ls -ld $(dirname "${AI_HOME}")")"
    mkdir -p "${AI_HOME}/bin" "${AI_MODELS}"
    for folder in "${AI_HOME}" "${AI_HOME}/bin" "${AI_MODELS}"; do
        root_only "${folder}" \
            || fail "$(t "${folder} gehört nicht allein root. Abgebrochen – prüfen: ls -ld ${folder}" "${folder} does not belong to root alone. Stopped – check: ls -ld ${folder}")"
    done
    chmod 755 "${AI_HOME}" "${AI_HOME}/bin" "${AI_MODELS}"
    local room=300
    [[ "${method}" == "build" ]] && room=1500
    check_free_space "${AI_HOME}" $(( size_mb + room ))

    # 1. llama-server
    say "$(t "llama-server installieren" "Installing llama-server")"
    if [[ "${method}" == "package" ]]; then
        if ! dpkg -s "${LLAMA_PACKAGE}" > /dev/null 2>&1; then
            apt-get update -q
            DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${LLAMA_PACKAGE}"
            echo "${LLAMA_PACKAGE}" >> "${AI_PACKAGES_FILE}"
        fi
        ln -sfn "$(command -v llama-server)" "${AI_BIN}"
        server_label="llama.cpp $(dpkg-query -W -f='${Version}' "${LLAMA_PACKAGE}") ($(t "Paket" "package"))"
        built_with="package"
    elif ! ${rebuild} && [[ ! -L "${AI_BIN}" && "$(llama_build "${AI_BIN}")" == "${LLAMA_TAG#b}" ]]; then
        # Built before (e.g. only the model changes) – no second build of half an hour. "--rebuild"
        # builds anyway, e.g. after the processor type of a virtual machine was set to "host".
        note "$(t "llama.cpp ${LLAMA_TAG} ist schon gebaut (neu bauen: --rebuild)." "llama.cpp ${LLAMA_TAG} is built already (build again: --rebuild).")"
        server_label="llama.cpp ${LLAMA_TAG} ($(t "aus dem Quelltext" "built from source"))"
        built_with="$(local_value built_with)"
    else
        DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends build-essential cmake git ca-certificates
        rm -rf "${AI_SOURCE_DIR}"
        mkdir -p "${AI_SOURCE_DIR}"
        git -c advice.detachedHead=false clone --quiet --depth 1 --branch "${LLAMA_TAG}" "${LLAMA_REPOSITORY}" "${AI_SOURCE_DIR}/llama.cpp" \
            || fail "$(t "llama.cpp ${LLAMA_TAG} ließ sich nicht herunterladen." "llama.cpp ${LLAMA_TAG} could not be downloaded.")"
        [[ "$(git -C "${AI_SOURCE_DIR}/llama.cpp" rev-parse HEAD)" == "${LLAMA_COMMIT}" ]] \
            || fail "$(t "Der Quelltext von llama.cpp ${LLAMA_TAG} ist nicht der erwartete (Commit ${LLAMA_COMMIT}). Abgebrochen." "The source of llama.cpp ${LLAMA_TAG} is not the expected one (commit ${LLAMA_COMMIT}). Stopped.")"
        note "$(t "Bauen – auf einem Raspberry Pi dauert das 15 bis 40 Minuten …" "Building – on a Raspberry Pi this takes 15 to 40 minutes …")"
        if ! cmake -S "${AI_SOURCE_DIR}/llama.cpp" -B "${AI_SOURCE_DIR}/build" -DCMAKE_BUILD_TYPE=Release \
                -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
                -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON > "${AI_HOME}/build.log" 2>&1 \
            || ! cmake --build "${AI_SOURCE_DIR}/build" --config Release --target llama-server \
                -j "$(build_jobs "${cores}" "${memory}")" >> "${AI_HOME}/build.log" 2>&1; then
            fail "$(t "Das Bauen von llama.cpp schlug fehl; siehe ${AI_HOME}/build.log." "Building llama.cpp failed; see ${AI_HOME}/build.log.")"
        fi
        rm -f "${AI_BIN}"
        install -m 755 "${AI_SOURCE_DIR}/build/bin/llama-server" "${AI_BIN}"
        rm -rf "${AI_SOURCE_DIR}"
        server_label="llama.cpp ${LLAMA_TAG} ($(t "aus dem Quelltext" "built from source"))"
        # GGML_NATIVE: the build uses what this processor has – and only that (see "refresh").
        built_with="$(vector_flags "${cpuinfo}" "${architecture}")"
    fi

    # 2. The model
    say "$(t "Modell" "Model"): ${name}"
    local target="${AI_MODELS}/${file}"
    if [[ -n "${source_file}" ]]; then
        [[ "${source_file}" == "$(readlink -f "${target}")" ]] || install -m 644 "${source_file}" "${target}.partial"
    elif [[ -f "${target}" && "$(sha256_of "${target}")" == "${sha}" ]]; then
        note "$(t "schon da und geprüft" "already there and checked")"
    else
        curl -fL --proto '=https' --tlsv1.2 --retry 3 --continue-at - -o "${target}.partial" "$(model_field "${key}" url)" \
            || fail "$(t "Das Modell ließ sich nicht herunterladen. Ohne Internet: Datei auf den Server kopieren und --model DATEI angeben." "The model could not be downloaded. Without internet: copy the file to the server and use --model FILE.")"
    fi
    if [[ -f "${target}.partial" ]]; then
        actual="$(sha256_of "${target}.partial")"
        if [[ -n "${sha}" && "${actual}" != "${sha}" ]]; then
            rm -f "${target}.partial"
            fail "$(t "Die Prüfsumme des Modells stimmt nicht (erwartet ${sha}, erhalten ${actual}). Die Datei wurde gelöscht." "The checksum of the model does not match (expected ${sha}, got ${actual}). The file was deleted.")"
        fi
        sha="${actual}"
        chmod 644 "${target}.partial"
        mv "${target}.partial" "${target}"
    fi
    row 22 "SHA-256" "${sha} $(t "geprüft" "checked")"

    # 3. The service
    say "$(t "Dienst ${AI_UNIT} einrichten" "Setting up the service ${AI_UNIT}")"
    umask 022
    local extra
    extra="$(llama_extra_flags "${AI_BIN}")" || exit 1
    write_service_files "${target}" "${alias}" "${port}" "${threads}" "${MODEL_CONTEXT}" "${extra}" "${memory_max}"
    install -m 644 "${APP_DIR}/deploy/systemd/${AI_UNIT}" "/etc/systemd/system/${AI_UNIT}"
    systemctl daemon-reload
    systemctl enable --quiet "${AI_UNIT}"
    systemctl restart "${AI_UNIT}"
    local base="http://127.0.0.1:${port}/v1"
    note "$(t "Warten, bis das Modell geladen ist …" "Waiting for the model to load …")"
    if ! wait_for_server "${base}" 300; then
        journalctl -u "${AI_UNIT}" -n 20 --no-pager >&2 || true
        fail "$(t "Der Dienst ${AI_UNIT} antwortet nicht. Siehe: journalctl -u ${AI_UNIT}" "The service ${AI_UNIT} does not answer. See: journalctl -u ${AI_UNIT}")"
    fi
    write_local_file "${base}" "${alias}" "${name}" "${licence}" "${MODEL_CONTEXT}" "${threads}" "${server_label}" \
        "llama.cpp" "${physical}" "${built_with}"

    # 4. A test prompt
    say "$(t "Probe" "Test")"
    local result seconds reading writing
    if result="$(test_prompt "${base}" "${alias}")"; then
        read -r seconds reading writing <<<"${result}"
        row 22 "$(t "Antwort nach" "Answer after")" "${seconds} s"
        row 22 "$(t "Lesen" "Reading")" "${reading} $(t "Token pro Sekunde" "tokens per second")"
        row 22 "$(t "Schreiben" "Writing")" "${writing} $(t "Token pro Sekunde" "tokens per second")"
    else
        warn "$(t "Die Probe schlug fehl; der Dienst läuft aber. Siehe: journalctl -u ${AI_UNIT}" "The test failed, but the service runs. See: journalctl -u ${AI_UNIT}")"
    fi
    # The model used before goes, once the new one answers (unless --keep-model).
    local old
    if ! ${keep_model}; then
        for old in "${AI_MODELS}"/*.gguf; do
            [[ -f "${old}" && "${old}" != "${target}" ]] || continue
            rm -f "${old}"
            note "$(t "Bisheriges Modell gelöscht: $(basename "${old}")" "Model used before deleted: $(basename "${old}")")"
        done
    fi
    warn_vectors "${missing}" "${vm}"
    say "$(t "Fertig." "Done.")"
    note "$(t 'Einschalten in Rentalars: Einstellungen → KI → „Zusammenfassungen mit lokaler KI einschalten“.' 'Switch it on in Rentalars: Settings → AI → “Switch summaries with local AI on”.')"
}

do_register() {
    ${dry_run} || require_root
    [[ -n "${url}" && -n "${model_choice}" ]] || fail "$(t "register braucht --url und --model." "register needs --url and --model.")"
    url="${url%/}"
    is_model_name "${model_choice}" || fail "$(t "--model: nur Buchstaben, Ziffern und . _ : / - (höchstens 128 Zeichen)." "--model: only letters, digits and . _ : / - (at most 128 characters).")"
    is_loopback_url "${url}" || fail "$(t "Die lokale KI muss auf diesem Rechner laufen: --url http://127.0.0.1:PORT/v1" "The local AI must run on this machine: --url http://127.0.0.1:PORT/v1")"
    say "$(t "Eigenen Server als lokale KI eintragen" "Registering an own server as the local AI")"
    row 22 "URL" "${url}"
    row 22 "$(t "Modell" "Model")" "${model_choice}"
    row 22 "$(t "Für Rentalars" "For Rentalars")" "${AI_LOCAL_FILE}"
    if ${dry_run}; then
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    curl -fsS --max-time 10 "${url}/models" > /dev/null || fail "$(t "${url}/models antwortet nicht." "${url}/models does not answer.")"
    write_local_file "${url}" "${model_choice}" "${model_choice}" "" "${context}" 0 "$(t "eigener Server" "own server")" \
        "other" 0
    say "$(t "Fertig." "Done.")"
}

do_remove() {
    ${dry_run} || require_root
    say "$(t "Lokale KI entfernen" "Removing the local AI")"
    row 22 "$(t "Dienst" "Service")" "${AI_UNIT} $(t "anhalten und abschalten" "stop and disable")"
    row 22 "$(t "Dateien" "Files")" "${AI_LOCAL_FILE}, ${AI_ENV_FILE}, ${AI_DROP_IN_DIR}"
    if ${keep_model}; then
        row 22 "$(t "Programm" "Program")" "${AI_BIN} ($(t "Modelle bleiben" "the models stay"))"
    else
        row 22 "$(t "Programm, Modelle" "Program, models")" "${AI_HOME}"
    fi
    [[ -f "${AI_PACKAGES_FILE}" ]] && row 22 "$(t "Pakete" "Packages")" "$(tr '\n' ' ' < "${AI_PACKAGES_FILE}")"
    if ${dry_run}; then
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    # First Rentalars stops using it, then the service goes.
    rm -f "${AI_LOCAL_FILE}"
    systemctl disable --now --quiet "${AI_UNIT}" 2> /dev/null || true
    rm -rf "${AI_DROP_IN_DIR}"
    rm -f "${AI_ENV_FILE}"
    systemctl daemon-reload || true
    if [[ -f "${AI_PACKAGES_FILE}" ]]; then
        mapfile -t packages < "${AI_PACKAGES_FILE}"
        DEBIAN_FRONTEND=noninteractive apt-get remove -y -q "${packages[@]}" || warn "$(t "Pakete ließen sich nicht entfernen: ${packages[*]}" "Packages could not be removed: ${packages[*]}")"
        rm -f "${AI_PACKAGES_FILE}"
    fi
    if ${keep_model}; then
        rm -rf "${AI_HOME:?}/bin" "${AI_SOURCE_DIR:?}"
    else
        rm -rf "${AI_HOME}"
    fi
    say "$(t "Fertig. Rentalars fasst ab jetzt nicht mehr mit der lokalen KI zusammen; der Kurzüberblick ohne KI bleibt." "Done. Rentalars no longer summarises with the local AI; the short overview without AI stays.")"
    note "$(t "Die Werkzeuge zum Bauen (build-essential, cmake, git) bleiben installiert." "The build tools (build-essential, cmake, git) stay installed.")"
}

do_status() {
    # The processor first – also before anything is installed.
    local cpuinfo="${RENTALARS_AI_CPUINFO:-/proc/cpuinfo}" architecture="${RENTALARS_AI_ARCH:-}" missing vm="no"
    [[ -n "${architecture}" ]] || architecture="$(dpkg --print-architecture 2> /dev/null || uname -m)"
    missing="$(missing_vectors "${cpuinfo}" "${architecture}")"
    in_virtual_machine "${cpuinfo}" && vm="yes"
    say "$(t "Lokale KI" "Local AI")"
    row 22 "$(t "Prozessor" "Processor")" "$(cpu_model "${cpuinfo}") – $(t "$(physical_cores "${cpuinfo}") physische Kerne, $(logical_cpus "${cpuinfo}") logische" "$(physical_cores "${cpuinfo}") physical cores, $(logical_cpus "${cpuinfo}") logical")$([[ "${vm}" == "yes" ]] && t ", virtuelle Maschine" ", virtual machine")"
    if [[ -n "${missing}" ]]; then
        row 22 "AVX2/FMA" "$(t "FEHLT: ${missing}" "MISSING: ${missing}")"
    elif [[ "${architecture}" == "amd64" || "${architecture}" == "x86_64" ]]; then
        row 22 "AVX2/FMA" "$(t "vorhanden" "present")"
    fi
    if [[ -f "${AI_ENV_FILE}" ]]; then
        row 22 "Threads" "$(sed -n 's/^AI_THREADS=//p' "${AI_ENV_FILE}") $(t "(einer je physischem Kern)" "(one per physical core)")"
        row 22 "$(t "Zusatzoptionen" "Options")" "$(sed -n 's/^AI_EXTRA=//p' "${AI_ENV_FILE}")"
        row 22 "$(t "gebaut mit" "built with")" "$(local_value built_with | sed "s/^$/$(t "unbekannt" "unknown")/")"
        note "$(t 'Nach jedem Update übernimmt „sudo rentalars ai refresh“ die Einstellungen von selbst.' 'After every update, “sudo rentalars ai refresh” takes over the settings by itself.')"
    fi
    if [[ ! -f "${AI_LOCAL_FILE}" ]]; then
        note "$(t "nicht installiert – sudo rentalars ai install" "not installed – sudo rentalars ai install")"
        warn_vectors "${missing}" "${vm}"
        return 0
    fi
    local local_url
    local_url="$(sed -n 's/^url = //p' "${AI_LOCAL_FILE}")"
    row 22 "URL" "${local_url}"
    row 22 "$(t "Modell" "Model")" "$(sed -n 's/^model_name = //p' "${AI_LOCAL_FILE}")"
    row 22 "$(t "Server" "Server")" "$(sed -n 's/^server = //p' "${AI_LOCAL_FILE}")"
    [[ -f "${AI_ENV_FILE}" ]] && row 22 "${AI_UNIT}" "$(systemctl is-active "${AI_UNIT}" 2> /dev/null || true)"
    if curl -fsS --max-time 5 "${local_url}/models" > /dev/null 2>&1; then
        row 22 "$(t "antwortet" "answers")" "$(t "ja" "yes")"
    else
        row 22 "$(t "antwortet" "answers")" "$(t "NEIN" "NO")"
    fi
    warn_vectors "${missing}" "${vm}"
}

# --- refresh ---------------------------------------------------------------------------------------
# What a new version of Rentalars sets up for the service, taken over without downloading, building or
# installing anything and without changing the model – see the top of this file.

# The work of "refresh"; may fail – do_refresh catches it.
refresh_local_ai() {
    local kind cpuinfo architecture device meminfo physical missing vm="no" fast memory
    local model alias port context threads extra memory_max key old_threads old_extra old_memory url
    local changed=false summary recommended built_with
    [[ -f "${AI_ENV_FILE}" ]] || fail "$(t "${AI_ENV_FILE} fehlt." "${AI_ENV_FILE} is missing.")"
    [[ -x "${AI_BIN}" ]] || fail "$(t "${AI_BIN} fehlt." "${AI_BIN} is missing.")"
    # Root writes here – only where nobody else can; llama-server is checked where it is run.
    local folder
    for folder in "$(dirname "${AI_ENV_FILE}")" "$(dirname "${AI_LOCAL_FILE}")" "$(dirname "${AI_DROP_IN_DIR}")"; do
        root_only "${folder}" || fail "$(t "${folder} gehört nicht allein root." "${folder} does not belong to root alone.")"
    done

    cpuinfo="${RENTALARS_AI_CPUINFO:-/proc/cpuinfo}" architecture="${RENTALARS_AI_ARCH:-}"
    device="${RENTALARS_AI_DEVICE_MODEL:-${DEVICE_MODEL_FILE}}" meminfo="${RENTALARS_AI_MEMINFO:-${MEMORY_INFO_FILE}}"
    [[ -n "${architecture}" ]] || architecture="$(dpkg --print-architecture 2> /dev/null || uname -m)"
    physical="$(physical_cores "${cpuinfo}")"
    (( physical > 0 )) || physical="$(nproc 2> /dev/null || echo 1)"
    missing="$(missing_vectors "${cpuinfo}" "${architecture}")"
    if in_virtual_machine "${cpuinfo}"; then vm="yes"; fi
    fast="$(fast_processor "${cpuinfo}" "${architecture}" "$(device_model "${device}")")"
    memory="$(memory_mb "${meminfo}")"

    model="$(env_value "${AI_ENV_FILE}" AI_MODEL)" alias="$(env_value "${AI_ENV_FILE}" AI_ALIAS)"
    port="$(env_value "${AI_ENV_FILE}" AI_PORT)" context="$(env_value "${AI_ENV_FILE}" AI_CONTEXT)"
    [[ -n "${model}" && -n "${alias}" && -n "${port}" ]] \
        || fail "$(t "${AI_ENV_FILE} ist unvollständig." "${AI_ENV_FILE} is incomplete.")"
    old_threads="$(env_value "${AI_ENV_FILE}" AI_THREADS)" old_extra="$(env_value "${AI_ENV_FILE}" AI_EXTRA)"
    old_memory="$(sed -n 's/^MemoryMax=//p' "${AI_DROP_IN_DIR}/50-limits.conf" 2> /dev/null | tail -n 1)"

    threads="$(model_threads "${physical}")"
    extra="$(llama_extra_flags "${AI_BIN}")"
    key="$(model_key_of "${alias}")"
    if [[ -n "${key}" ]]; then
        memory_max="$(model_field "${key}" memory)"
    else
        memory_max="${old_memory:-3G}"  # an own model file: its limit stays
    fi
    if [[ "${threads}" != "${old_threads}" || "${extra}" != "${old_extra}" || "${memory_max}" != "${old_memory}" ]]; then
        changed=true
    fi

    if ${dry_run}; then
        say "$(t "Lokale KI: Einstellungen übernehmen" "Local AI: taking over the settings")"
        row 22 "Threads" "${old_threads:-?} → ${threads}"
        row 22 "$(t "Zusatzoptionen" "Options")" "${old_extra:-–} → ${extra:-–}"
        row 22 "MemoryMax" "${old_memory:-?} → ${memory_max}"
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi

    umask 022
    if ${changed}; then
        write_service_files "${model}" "${alias}" "${port}" "${threads}" "${context:-${MODEL_CONTEXT}}" "${extra}" \
            "${memory_max}"
        "${AI_SYSTEMCTL}" daemon-reload
        if "${AI_SYSTEMCTL}" is-enabled --quiet "${AI_UNIT}" 2> /dev/null; then
            "${AI_SYSTEMCTL}" restart "${AI_UNIT}"
            url="$(local_value url)"
            wait_for_server "${url:-http://127.0.0.1:${port}/v1}" 120 \
                || warn "$(t "Der Dienst ${AI_UNIT} antwortet noch nicht. Siehe: journalctl -u ${AI_UNIT}" "The service ${AI_UNIT} does not answer yet. See: journalctl -u ${AI_UNIT}")"
        fi
    fi
    # The lines in ai-local.conf (they need no restart: Rentalars reads the file at every use).
    [[ "$(local_value server_kind)" == "llama.cpp" ]] || config_set "${AI_LOCAL_FILE}" local_ai server_kind llama.cpp
    [[ "$(local_value physical_cores)" == "${physical}" ]] || config_set "${AI_LOCAL_FILE}" local_ai physical_cores "${physical}"
    [[ "$(local_value threads)" == "${threads}" ]] || config_set "${AI_LOCAL_FILE}" local_ai threads "${threads}"
    chmod 644 "${AI_LOCAL_FILE}"

    if ${changed}; then
        summary="$(t "${threads} Threads" "${threads} threads")"
        if [[ " ${extra} " == *" --reasoning off "* ]]; then
            summary="$(t "Nachdenken aus" "thinking off"), ${summary}"
        fi
        say "$(t "Lokale KI: Einstellungen übernommen (${summary})." "Local AI: settings taken over (${summary}).")"
    else
        say "$(t "Lokale KI: unverändert." "Local AI: unchanged.")"
    fi

    # Hints – nothing is switched: a model is a large file, a build takes its time.
    recommended="$(choose_model "${memory}" "${physical}" "${fast}")"
    if [[ -n "${key}" && -n "${recommended}" && "${recommended}" != "${key}" ]]; then
        note "$(t "Für diesen Rechner empfohlen: $(model_field "${recommended}" name). Wechseln mit:" "Recommended for this machine: $(model_field "${recommended}" name). Switch with:")"
        note "    sudo rentalars ai install --model ${recommended}"
    fi
    built_with="$(local_value built_with)"
    if [[ -z "${missing}" && ( "${architecture}" == "amd64" || "${architecture}" == "x86_64" ) \
            && -n "${built_with}" && "${built_with}" != "package" && "${built_with}" != *avx2* ]]; then
        note "$(t "llama-server wurde auf einem Prozessor ohne AVX2 gebaut; dieser hat es jetzt. Neu bauen mit:" "llama-server was built on a processor without AVX2; this one has it now. Build again with:")"
        note "    sudo rentalars ai install --rebuild"
    fi
    warn_vectors "${missing}" "${vm}"
    return 0
}

# Succeeds if the local AI was installed here by "install" – not registered, not missing: installed_here
installed_here() {
    local kind
    [[ -f "${AI_LOCAL_FILE}" ]] || return 1
    kind="$(local_value server_kind)"
    if [[ -z "${kind}" ]]; then
        # A file: installed here if the service has its options, otherwise a registered server.
        [[ -f "${AI_ENV_FILE}" ]]
        return
    fi
    [[ "${kind}" == "llama.cpp" ]]
}

# NFA-076: "refresh" first installs the packages of the system that this version needs and the server lacks
# (lib.sh, added_packages – ffmpeg for the videos in the chat). It lives here because "refresh" is the only script
# of the NEW version that the update from an older version runs: the update.sh of those versions
# calls "ai.sh refresh" right after switching to the new release, and knows nothing of the packages itself. Later
# updates install them in update.sh (step 3); then nothing is missing here. Nothing missing: nothing is done, apt
# is not called – so also at every start through rentalars-ai-refresh.timer. A failure is warned about, never
# fails the caller. The tests of "refresh" (tests/unit/test_084_ai.py) change nothing on the computer; those of
# tests/deploy/test_system.sh give dpkg-query and apt-get of their own.
refresh_packages() {
    if [[ -n "${AI_TEST_ROOT}" && -z "${RENTALARS_APT_GET:-}" ]]; then
        return 0
    fi
    local missing own_lib
    own_lib="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"
    mapfile -t missing < <(missing_added_packages "${own_lib}")
    (( ${#missing[@]} > 0 )) || return 0
    if ${dry_run}; then
        note "$(t "Pakete: würde installieren: ${missing[*]}" "Packages: would install: ${missing[*]}")"
    elif [[ ${EUID} -ne 0 && -z "${AI_TEST_ROOT}" ]]; then
        warn "$(t "Es fehlen Pakete (${missing[*]}); installieren mit Administratorrechten: sudo apt install ${missing[*]}" "Packages are missing (${missing[*]}); install them with administrator rights: sudo apt install ${missing[*]}")"
    else
        install_added_packages "${own_lib}" || true
    fi
    return 0
}

# "refresh": never fails its caller (rentalars update) – a local AI that cannot be refreshed is warned about.
# No local AI, or a registered server: nothing to do, nothing said (except packages being installed, above).
do_refresh() {
    refresh_packages
    installed_here || return 0
    if [[ ${EUID} -ne 0 && -z "${AI_TEST_ROOT}" ]] && ! ${dry_run}; then
        warn "$(t "Lokale KI: Einstellungen nur mit Administratorrechten übernehmbar: sudo rentalars ai refresh" "Local AI: settings can only be taken over with administrator rights: sudo rentalars ai refresh")"
        return 0
    fi
    # In /run, which only root may write to – not /run/lock, where anybody could put a link to a file of root's
    # (as deploy/address.py does).
    local lock="${AI_TEST_ROOT}/run/rentalars-ai-refresh.lock" status
    mkdir -p "$(dirname "${lock}")" 2> /dev/null || true
    set +e
    (
        set -e
        # One refresh at a time: the update and the timer may meet.
        root_only "$(dirname "${lock}")"
        exec 9> "${lock}" && flock -w 300 9
        refresh_local_ai
    )
    status=$?
    set -e
    if (( status != 0 )); then
        warn "$(t "Lokale KI: Einstellungen nicht übernommen; sie läuft weiter wie bisher. Prüfen: sudo rentalars ai status" "Local AI: settings not taken over; it goes on running as before. Check: sudo rentalars ai status")"
    fi
    return 0
}

case "${command}" in
    install)  do_install ;;
    register) do_register ;;
    remove)   do_remove ;;
    status)   do_status ;;
    refresh)  do_refresh ;;
    ""|help)  usage ;;
    *)        fail "$(t "Unbekannter Befehl: ai ${command}. Möglich: install, register, remove, status, refresh." "Unknown command: ai ${command}. Possible: install, register, remove, status, refresh.")" ;;
esac
