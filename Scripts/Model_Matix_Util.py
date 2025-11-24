# --- MODEL_MATRIX.PY ---
import re


def extract_llama_metrix(log_content):
    data = {}

    # --- GPU Name ---
    gpu_name_pattern = r"using device CUDA0 \((.*?)\)"
    match = re.search(gpu_name_pattern, log_content)
    data['GPU Name'] = match.group(1) if match else "!!! Data Not Found !!!"

    # --- Available VRAM ---
    vram_pattern = r"llama_model_load_from_file_impl:.*? - (\d+)\sMiB\sfree"
    match = re.search(vram_pattern, log_content)
    data['Available VRAM'] = f"{match.group(1)} MiB" if match else "0 MiB"

    # --- GPU Weights Buffer ---
    gpu_pattern = r"CUDA0 model buffer size\s+=\s+([\d.]+)\sMiB"
    match = re.search(gpu_pattern, log_content)
    data['GPU Weights Buffer'] = f"{match.group(1)} MiB" if match else "0 MiB"

    # --- CPU Spillover Buffer ---
    cpu_pattern = r"CPU_Mapped model buffer size\s+=\s+([\d.]+)\sMiB"
    match = re.search(cpu_pattern, log_content)
    data['CPU Spillover Buffer'] = f"{match.group(1)} MiB" if match else "0.0 MiB"

    # --- Context Length (runtime) ---
    ctx_pattern = r"llama_context: n_ctx\s+=\s+(\d+)"
    match = re.search(ctx_pattern, log_content)
    data['Runtime Context'] = f"{match.group(1)} tokens" if match else "N/A"

    # --- Total Configured Context ---
    ctx_train_pattern = r"print_info: n_ctx_train\s+=\s+(\d+)" 
    match = re.search(ctx_train_pattern, log_content)
    data['Total Context'] = f"{match.group(1)} tokens" if match else "N/A"

    # --- KV Cache Sizes ---
    kv_gpu_pattern = r"CUDA0 KV buffer size\s+=\s+([\d.]+)\sMiB" 
    match = re.search(kv_gpu_pattern, log_content)
    data['GPU KV Cache'] = f"{match.group(1)} MiB" if match else "0.0 MiB"

    kv_cpu_pattern = r"CPU KV buffer size\s+=\s+([\d.]+)\sMiB"
    match = re.search(kv_cpu_pattern, log_content)
    data['CPU KV Cache'] = f"{match.group(1)} MiB" if match else "0.0 MiB"

    # --- Total Layers ---
    layers_pattern = r"print_info: n_layer\s+=\s+(\d+)"
    match = re.search(layers_pattern, log_content)
    data['Total Layers'] = match.group(1) if match else "N/A"

    return data


def print_llama_matrix(log_file, GPU_LAYERS, N_THREADS, CONTEXT):
    with open(log_file, "r") as f:
        log_content = f.read()

    metrics = extract_llama_metrix(log_content)

    # If GPU_LAYERS is -1 (not set), use the extracted total layers
    total_layers_extracted = metrics.get('Total Layers')
    GPU_LAYERS = GPU_LAYERS if GPU_LAYERS != -1 else total_layers_extracted

    # --- Total Model Size ---
    try:
        # Helper function to safely extract the MiB float value, defaulting to 0.0
        def get_mib_float(key):
            value_str = metrics.get(key, "0 MiB").split()[0]
            # Handle cases where value might be "0" or missing
            return float(value_str) if value_str.replace('.', '', 1).isdigit() else 0.0

        # Summing all four memory components
        gpu_weights = get_mib_float("GPU Weights Buffer")
        cpu_spillover = get_mib_float("CPU Spillover Buffer")
        gpu_kv = get_mib_float("GPU KV Cache")
        cpu_kv = get_mib_float("CPU KV Cache")
        # Calculate GPU overflow
        Calculated_overflow = round(
            (get_mib_float('GPU Weights Buffer') +
             get_mib_float('GPU KV Cache')) - get_mib_float('Available VRAM'),
            2
        )

        # Adjust CPU spillover buffer
        cpu_spillover_buffer = round(
            get_mib_float('CPU Spillover Buffer') +
            Calculated_overflow if Calculated_overflow > 0 else get_mib_float(
                'CPU Spillover Buffer'),
            2
        )
        cpu_spillover_buffer = f"{cpu_spillover_buffer} MiB"

        total_size = f"{gpu_weights + cpu_spillover + gpu_kv + cpu_kv:.2f} MiB"
    except Exception as e:
        # Fallback if any unexpected error occurs during parsing/calculation
        total_size = "Not Available"

    # --- Fancy Table ---
    print(
        # Green Border | Yellow Title | Green Border
        f"\n\033[1;32m╭────────────────\033[1;33m LLaMA Snapshot\033[0m\033[1;32m ────────────────╮\033[0m"
        f"\n\033[1;32m│\033[0m \t\033[1;97m 🦙 Model Loading Successful! 🦙\033[0m\t\033[1;32m │\033[0m"
        f"\n\033[1;32m├────────────────────────────────────────────────┤\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;96m• Configured Parameters\t\033[0m\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Layers On GPU\033[0m      : \033[1m{GPU_LAYERS:<4}\033[0m\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  CPU Threads\033[0m        : \033[1m{N_THREADS:<4}\033[0m\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Configured Context\033[0m : \033[1m{CONTEXT:<6}\033[0m\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m├────────────────────────────────────────────────┤\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;96m• Runtime Stats\t\t\033[0m\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Total Layers\033[0m       : \033[1m{metrics['Total Layers']:<10}\t\033[0m\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Runtime Context\033[0m    : \033[1m{metrics['Runtime Context']:<10}\t\033[0m\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Total Context\033[0m      : \033[1m{metrics['Total Context']:<10}\t\033[0m\t\033[1;32m │\033[0m"
        f"\n\033[1;32m├────────────────────────────────────────────────┤\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;96m• GPU Memory\t\033[0m\t\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  GPU Name\033[0m           : \033[1m{metrics['GPU Name']:<15}\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Available VRAM\033[0m     : \033[1m{metrics['Available VRAM']:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  GPU Weights Buffer\033[0m : \033[1m{metrics['GPU Weights Buffer']:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  GPU KV Cache\033[0m       : \033[1m{metrics['GPU KV Cache']:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m├────────────────────────────────────────────────┤\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;96m• CPU Memory\t\033[0m\t\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Spillover Buffer\033[0m   : \033[1m{cpu_spillover_buffer:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  CPU KV Cache\033[0m       : \033[1m{metrics['CPU KV Cache']:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m├────────────────────────────────────────────────┤\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;96m• Total\t\033[0m\t\t\t\t\033[1;32m │\033[0m"
        f"\n\033[1;32m│\033[0m \033[1;33m  Model Weights Size\033[0m : \033[1m{total_size:<10}\t\t\033[0m\033[1;32m │\033[0m"
        f"\n\033[1;32m╰────────────────────────────────────────────────╯\033[0m\n"
    )
