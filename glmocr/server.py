"""GLM-OCR SDK Flask service."""

import os
import sys
import traceback
import multiprocessing
import gc
from typing import TYPE_CHECKING

try:
    from flask import Flask, request, jsonify

    _FLASK_IMPORT_ERROR = None
except ImportError as e:  # pragma: no cover
    Flask = None  # type: ignore
    request = None  # type: ignore
    jsonify = None  # type: ignore
    _FLASK_IMPORT_ERROR = e

from glmocr.pipeline import Pipeline
from glmocr.config import load_config
from glmocr.utils.logging import get_logger, configure_logging

if TYPE_CHECKING:
    from glmocr.config import GlmOcrConfig

logger = get_logger(__name__)

os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""


def create_app(config: "GlmOcrConfig") -> Flask:
    """Create a Flask app.

    Args:
        config: GlmOcrConfig instance.

    Returns:
        Flask app instance.
    """
    if Flask is None:
        raise ImportError(
            "Flask server support requires the optional server extra. "
            "Install with: pip install 'glmocr[server]'"
        ) from _FLASK_IMPORT_ERROR

    app = Flask(__name__)

    # Create pipeline with typed config
    pipeline = Pipeline(config=config.pipeline)

    # Store pipeline and config in app.config
    app.config["pipeline"] = pipeline
    app.config["doc_config"] = config

    @app.route("/glmocr/parse", methods=["POST"])
    def parse():
        """Document parsing endpoint.

        Request:
            {
                "images": ["url1", "url2", ...],  # image URLs (http/https/file/data)
            }

        Response:
            {
                "json_result": {...},
                "markdown_result": "..."
            }
        """
        # Try to parse the return_base64 flag
        return_base64 = False

        if request.mimetype.startswith("multipart/form-data"):
            # Form field URLs
            images = list(request.form.getlist("images"))
            if isinstance(images, str):
                images = [images]
            
            # Form field flag
            return_base64_str = request.form.get("return_base64", "true").lower()
            return_base64 = return_base64_str == "true" or return_base64_str == "1"

            messages = [{"role": "user", "content": []}]
            
            # Files attached
            for file_key in request.files:
                for file_obj in request.files.getlist(file_key):
                    if file_obj.filename:
                        file_bytes = file_obj.read()
                        if file_bytes:
                            if file_obj.filename.lower().endswith(".pdf"):
                                import tempfile
                                from glmocr.utils.image_utils import pdf_to_images_pil_iter
                                temp_dir = tempfile.mkdtemp()
                                try:
                                    for idx, img in enumerate(pdf_to_images_pil_iter(file_bytes)):
                                        img_path = os.path.join(temp_dir, f"page_{idx}.png")
                                        img.save(img_path, format="PNG")
                                        images.append(img_path)
                                        img.close()
                                except Exception as e:
                                    logger.error("Error converting PDF %s to images: %s", file_obj.filename, e)
                            else:
                                messages[0]["content"].append({"type": "image_bytes", "data": file_bytes})

            for image_url in images:
                if isinstance(image_url, str) and image_url.strip():
                    messages[0]["content"].append(
                        {"type": "image_url", "image_url": {"url": image_url}}
                    )

            if not messages[0]["content"]:
                return jsonify({"error": "No images provided in form or files"}), 400

            request_data = {"messages": messages}

        elif request.mimetype == "application/json":
            try:
                data = request.json
            except Exception:
                return jsonify({"error": "Invalid JSON payload"}), 400

            images = data.get("images", [])
            if isinstance(images, str):
                images = [images]

            if not images:
                return jsonify({"error": "No images provided"}), 400

            return_base64 = data.get("return_base64", True)

            import tempfile
            from glmocr.utils.image_utils import pdf_to_images_pil_iter
            
            expanded_images = []
            for img_src in images:
                if isinstance(img_src, str) and img_src.lower().endswith(".pdf") and os.path.isfile(img_src):
                    temp_dir = tempfile.mkdtemp()
                    try:
                        for idx, img in enumerate(pdf_to_images_pil_iter(img_src)):
                            img_path = os.path.join(temp_dir, f"page_{idx}.png")
                            img.save(img_path, format="PNG")
                            expanded_images.append(img_path)
                            img.close()
                    except Exception as e:
                        logger.error("Error converting PDF %s to images: %s", img_src, e)
                        expanded_images.append(img_src)
                else:
                    expanded_images.append(img_src)
            images = expanded_images

            messages = [{"role": "user", "content": []}]
            for image_url in images:
                if isinstance(image_url, str) and image_url.strip():
                    messages[0]["content"].append(
                        {"type": "image_url", "image_url": {"url": image_url}}
                    )

            request_data = {"messages": messages}
            
        else:
            return (
                jsonify(
                    {"error": "Invalid Content-Type. Expected 'application/json' or 'multipart/form-data'."}
                ),
                400,
            )

        try:
            # Pipeline.process() yields one result per input unit; merge for single response
            results = list(
                pipeline.process(
                    request_data,
                    save_layout_visualization=False,
                    return_base64=return_base64,
                )
            )
            if not results:
                return (
                    jsonify({"json_result": None, "markdown_result": ""}),
                    200,
                )
            if len(results) == 1:
                r = results[0]
                return (
                    jsonify(
                        {
                            "json_result": r.json_result,
                            "markdown_result": r.markdown_result or "",
                        }
                    ),
                    200,
                )
            # Multiple units: merge json as list, markdown with separator
            json_result = [r.json_result for r in results]
            markdown_result = "\n\n---\n\n".join(
                r.markdown_result or "" for r in results
            )
            return (
                jsonify(
                    {
                        "json_result": json_result,
                        "markdown_result": markdown_result,
                    }
                ),
                200,
            )

        except Exception as e:
            logger.error("Parse error: %s", e)
            logger.debug(traceback.format_exc())
            return jsonify({"error": f"Parse error: {str(e)}"}), 500
        
        finally:
            gc.collect()

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    return app


def main():
    """Main entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(description="GlmOcr Server")
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    args = parser.parse_args()

    # Use spawn for multiprocessing
    multiprocessing.set_start_method("spawn", force=True)

    app = None

    try:
        config = load_config(args.config)

        # Configure logging
        log_level = args.log_level or config.logging.level
        configure_logging(level=log_level)

        # Create app with typed config
        app = create_app(config)

        # Start pipeline
        pipeline = app.config["pipeline"]
        pipeline.start()

        # Start Flask service
        server_config = config.server
        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "GlmOcr Server starting on %s:%d...", server_config.host, server_config.port
        )
        logger.info("API endpoint: /glmocr/parse")
        logger.info("=" * 60)
        logger.info("")

        if not server_config.debug:
            try:
                import waitress
                logger.info("Using Waitress WSGI server.")
                waitress.serve(app, host=server_config.host, port=server_config.port)
            except ImportError:
                logger.warning("Waitress not found. Falling back to Flask dev server. For production, install waitress: pip install waitress")
                app.run(
                    debug=server_config.debug,
                    host=server_config.host,
                    port=server_config.port,
                )
        else:
            logger.info("Running Flask in debug mode.")
            app.run(
                debug=server_config.debug,
                host=server_config.host,
                port=server_config.port,
            )

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error("Error: %s", e)
        logger.debug(traceback.format_exc())
        sys.exit(1)
    finally:
        # Stop pipeline
        if app is not None and "pipeline" in app.config:
            app.config["pipeline"].stop()


if __name__ == "__main__":
    main()
