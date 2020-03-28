import os
import asyncio
import shlex
from pathlib import Path
import logging
import argparse

from aiohttp import web, web_exceptions
import aiofiles

# values could be overridden by args or env variables

ADS_APP_DEFAULT_CONFIG = {
    'interval_secs': 0,
    'archives_folder_path': Path('/app/test_photos')
}

CHUNK_SIZE = 1024
ZIP_GENERATE_CMD_TMP = "zip -q - -r {folder_path} -i '*.jpg' '*.png'"


async def get_404_content():
    """Return content of the 404 page."""
    async with aiofiles.open('404.html', mode='r') as index_file:
        return await index_file.read()


async def archivate(request: web.Request):
    folder_to_download = request.app['archives_folder_path'].joinpath(request.match_info["archive_hash"])
    logging.debug(f"Searching for files in {folder_to_download.as_posix()}")
    #  check for unexisting folders and path injections
    if not folder_to_download.exists() or '.' in request.match_info["archive_hash"]:
        logging.debug(f"'{folder_to_download.as_posix()}' doesn't exists ")
        return web_exceptions.HTTPNotFound(text=await get_404_content(), content_type='text/html')

    logging.debug(f"{folder_to_download.as_posix()} has been found")
    response = web.StreamResponse()
    response.headers['Content-Disposition'] = 'attachment; filename="archive.zip"'
    await response.prepare(request)

    cmd_to_zip = shlex.split(ZIP_GENERATE_CMD_TMP.format(folder_path=folder_to_download.absolute()))
    archive_stream_proc = await asyncio.create_subprocess_exec(*cmd_to_zip, stdout=asyncio.subprocess.PIPE)
    logging.debug(f"Starting download pid: {archive_stream_proc.pid} with delay {request.app['interval_secs']} secs.")

    try:
        while True:
            chunk = await archive_stream_proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                break
            logging.debug('Sending archive chunk ...')
            await response.write(chunk)
            await asyncio.sleep(request.app['interval_secs'])
    except asyncio.CancelledError:
        logging.debug("Download was interrupted")
        logging.debug(f"Killing process {archive_stream_proc.pid}")
        archive_stream_proc.kill()
        raise
    finally:
        await archive_stream_proc.wait()
        response.force_close()

    return response


async def handle_index_page(request):
    """Shows index page of the service."""
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def configure_app(application):
    parser = argparse.ArgumentParser()

    parser.add_argument('--debug', help='init logging with DEBUG level', action='store_true')
    parser.add_argument('--delay', help='set delay before send next chunk of data', default=0, type=float)
    parser.add_argument('--photo_path', help='override root path for photos folder', default=None)

    args = parser.parse_args()

    (args.debug or os.getenv('ADS_DEBUG', 'false').lower() == 'true') and logging.basicConfig(level=logging.DEBUG)

    # command line arguments have priority before env variables
    application['interval_secs'] = args.delay or os.getenv('ADS_DELAY', 0) or ADS_APP_DEFAULT_CONFIG['interval_secs']

    application['archives_folder_path'] = Path(
        args.photo_path or os.getenv('ADS_PHOTO_PATH', '') or ADS_APP_DEFAULT_CONFIG['archives_folder_path'].absolute())


if __name__ == '__main__':
    app = web.Application()
    configure_app(app)
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
    ])
    web.run_app(app)
