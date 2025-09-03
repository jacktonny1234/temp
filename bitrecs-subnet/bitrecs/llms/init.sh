#!/bin/bash

# ================================
# CONFIGURATION
# ================================

# Declare an associative array mapping coldkey -> hotkey list
declare -A coldkey_hotkeys

###5DYH

coldkey_hotkeys["pub122-1"]="net122_uid127"
# Default provider and model
default_provider="OPEN_ROUTER"
default_model="google/gemini-2.5-flash-lite-preview-06-17"
# default_model="google/gemini-2.0-flash-001"
# default_model="google/gemini-flash-1.5"

# Declare overrides as associative arrays (Bash 4+ required)
declare -A provider_override
declare -A model_override
declare -A miner_script_override

# model_override["net122_uid97"]="google/gemini-2.5-flash-lite-preview-06-17"
export OPENROUTER_API_KEY="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,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,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,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,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,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,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,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,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,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"
# Base port
base_port=10000
port_offset=0

# ================================
# MAIN LOOP
# ================================

for coldkey in "${!coldkey_hotkeys[@]}"; do
    hotkeys_string="${coldkey_hotkeys[$coldkey]}"
    hotkeys=($hotkeys_string)

    echo "---------------------------------------------"
    echo "Starting miners for coldkey: $coldkey"
    echo "---------------------------------------------"

    for hotkey in "${hotkeys[@]}"; do
        port=$((base_port + port_offset))
        port_offset=$((port_offset + 1))

        # Use override if set, else default
        provider="${provider_override[$hotkey]:-$default_provider}"
        model="${model_override[$hotkey]:-$default_model}"
        miner_script="${miner_script_override[$hotkey]:-./neurons/miner.py}"

        echo "Starting miner for hotkey: $hotkey"
        echo "  Coldkey: $coldkey"
        echo "  Provider: $provider"
        echo "  Model: $model"
        echo "  Miner Script: $miner_script"
        echo "  Port: $port"

        pm2 start "$miner_script" --name "new11-$hotkey" -- \
            --netuid 122 \
            --wallet.name "$coldkey" \
            --wallet.hotkey "$hotkey" \
            --logging.debug \
            --subtensor.network finney \
            --llm.provider "$provider" \
            --blacklist.force_validator_permit \
            --llm.model "$model" \
            --subtensor.network ws://5.9.10.7:9944 \
            --axon.port "$port"
       sleep 1
    done
done
