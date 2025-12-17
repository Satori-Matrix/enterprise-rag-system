"""
CPU Server - Query serving only (no document upload)
"""
import sys
sys.path.insert(0, '/app')

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env", override=False)

from lightrag.api.lightrag_server import create_app, configure_logging, check_and_install_dependencies, display_splash_screen
from lightrag.api.config import global_args, update_uvicorn_mode_config
from lightrag.api.utils_api import check_env_file
import uvicorn

def main():
    if not check_env_file():
        sys.exit(1)
    check_and_install_dependencies()
    from multiprocessing import freeze_support
    freeze_support()
    configure_logging()
    update_uvicorn_mode_config()
    display_splash_screen(global_args)
    
    app = create_app(global_args)
    print("✅ CPU Query Server ready (PostgreSQL storage)")
    
    uvicorn_config = {
        "app": app,
        "host": global_args.host,
        "port": global_args.port,
        "log_config": None,
    }
    if global_args.ssl:
        uvicorn_config.update({
            "ssl_certfile": global_args.ssl_certfile,
            "ssl_keyfile": global_args.ssl_keyfile,
        })
    uvicorn.run(**uvicorn_config)

if __name__ == "__main__":
    main()
