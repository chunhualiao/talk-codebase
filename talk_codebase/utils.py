import glob
import multiprocessing
import os
import sys
import logging
import tiktoken
from git import Repo
from langchain import FAISS
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

from talk_codebase.consts import LOADER_MAPPING, EXCLUDE_FILES

from git.exc import GitCommandError

# Set up logging
logging.basicConfig(filename=os.path.expanduser('~/.talk-codebase.log'), level=logging.INFO, filemode='a')

def get_repo(root_dir):
    try:
        return Repo(root_dir)
    except:
        return None


def is_ignored(path, root_dir):
    try: 
        repo = get_repo(root_dir)
        if repo is None:
            return False
        if not os.path.exists(path):
            return False
        ignored = repo.ignored(path)
        return len(ignored) > 0
    except GitCommandError as e:
        print("Encountered Git error with path: ", path)
        logging.error("Failed to check file {} in is_ignored(). Reason: {}".format(path, e))
        return False


class StreamStdOut(StreamingStdOutCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_llm_start(self, serialized, prompts, **kwargs):
        sys.stdout.write("🤖 ")

    def on_llm_end(self, response, **kwargs):
        sys.stdout.write("\n")
        sys.stdout.flush()


def load_files(root_dir):
    num_cpus = multiprocessing.cpu_count()
    with multiprocessing.Pool(num_cpus) as pool:
        futures = []
        for file_path in glob.glob(os.path.join(root_dir, '**/*'), recursive=True):
            if is_ignored(file_path, root_dir):
                continue
            if any(
                    file_path.endswith(exclude_file) for exclude_file in EXCLUDE_FILES):
                continue
            for ext in LOADER_MAPPING:
                if file_path.endswith(ext):
                    print('\r' + f'📂 Loading files: {file_path}')
                    logging.info(f'📂 Loading files: {file_path}')  # Log to the file instead of print
                    try: 
                        args = LOADER_MAPPING[ext]['args']
                        loader = LOADER_MAPPING[ext]['loader'](file_path, *args)
                        futures.append(pool.apply_async(loader.load))
                    except Exception as e:
                        logging.error("Failed to load file {}. Reason: {}".format(file_path, e))
                        continue    
        docs = []
        for future in futures:
            try: 
                docs.extend(future.get())
            except Exception as e:
                logging.error("Failed to get result from future. Reason: {}".format(e))   
                continue
    return docs


def calculate_cost(texts, model_name):
    enc = tiktoken.encoding_for_model(model_name)
    all_text = ''.join([text.page_content for text in texts])
    tokens = enc.encode(all_text)
    token_count = len(tokens)
    cost = (token_count / 1000) * 0.0004
    return cost


def get_local_vector_store(embeddings, path):
    try:
        return FAISS.load_local(path, embeddings)
    except:
        return None
