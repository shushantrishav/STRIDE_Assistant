# --- MODEL_INIT.PY ---
import os
import contextlib
from dotenv import load_dotenv
from llama_cpp import Llama
from Scripts.Model_Matix_Util import print_llama_matrix

# Log file (append mode)
LOG_FILE = "Logs/llama.log"
LOG_FILE_ALT = "Logs/llama_alt.log"

# Load environment variables from .env file
load_dotenv()

# Detect CPU cores dynamically
DEFAULT_THREADS = (os.cpu_count() or 4) // 2

# Get the model path from environment variable
LLM_Model = os.getenv("MODEL_PATH")
GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", -1))
N_THREADS = int(DEFAULT_THREADS)
CONTEXT = int(os.getenv("CONTEXT_SIZE", 8149))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 512))
UPDATE_BATCH_SIZE = int(os.getenv("UPDATE_BATCH_SIZE", 512))
VERBOSE = os.getenv("VERBOSE", "False").lower() in ("true", "1", "t")

# Load the model
def load_model() -> Llama:
    if not VERBOSE:
        LOG_FILE_LOAD = LOG_FILE_ALT
    else:
        LOG_FILE_LOAD = LOG_FILE

    with open(LOG_FILE_LOAD, "w") as f, contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        llm = Llama(
            # 1. Load the model parameters
            model_path=LLM_Model,
            n_ctx=CONTEXT,
            n_threads=N_THREADS,
            n_gpu_layers=GPU_LAYERS,
            offload_kqv=True,
            verbose=VERBOSE,
            # 2. Generation parameters
            temperature=0.95,
            top_p=0.95,
            top_k=50,
            repeat_penalty=1.1,
            presence_penalty=0.4,
            frequency_penalty=0.15,
            # 3. Performance tuning
            n_batch=BATCH_SIZE,
            n_ubatch=UPDATE_BATCH_SIZE
        )
    print_llama_matrix(LOG_FILE,GPU_LAYERS,N_THREADS,CONTEXT)
    return llm
