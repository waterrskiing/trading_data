import logging
import re
import requests
import subprocess
import zipfile

from bs4 import BeautifulSoup
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

LOG_FILE = 'log.txt'

def setup_logger():
    """Set up logger"""
    FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    logger = logging.getLogger()
    logger.handlers.clear()

    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(FORMAT))
    stdout_handler.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_FILE)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.setLevel(logging.DEBUG)

    logger.addHandler(handler)
    logger.addHandler(stdout_handler)
    return logger

def parse_user_config(config_path='user_config.ini'):
    """
    Parse user config from config file

    Parameters
    ----------
    config_path : str, optional
        path to config file, by default 'user_config.ini'

    Returns
    -------
    tuple
        tuple of variables retrieved from config file
    """
    config_path = (Path(__file__).parent / config_path).resolve()
    assert config_path.is_file()
    user_configs = ConfigParser()
    user_configs.read(config_path)
    return (user_configs.get('USER_DATA', 'source_webpage'),
            user_configs.get('USER_DATA', 'source_pattern'),
            user_configs.get('USER_DATA', 'abb_file'),
            user_configs.get('USER_DATA', 'dest_dir'),
            user_configs.get('USER_DATA', 'amibroker'))


def get_links(web_page, pattern):
    """
    Get trade data links from source web page

    Parameters
    ----------
    web_page : str
        the web page containing trade data
    pattern: str
        source file pattern on the web page

    Returns
    -------
    set
        set of links to trade data zip files
    """
    links = set()
    web_content = requests.get(web_page)
    soup = BeautifulSoup(web_content.text, features='html.parser')
    for a in soup.find_all('a', href=True):
        if re.match(pattern, a['href']):
            links.add(a['href'])
    return links

def download_unzip(trade_data_files_links, dest_dir):
    """
    Download trade data zip files and unzip into an iterim folder called SLGD

    Parameters
    ----------
    dest_dir: str
        destination dir of the data files
    """
    # Clean the dest dir prior to download + unzip
    for file_ in Path(dest_dir).iterdir():
        Path(file_).unlink()
    for link in trade_data_files_links:
        downloaded_slgd = rf'd:\Invest\AmibrokerData\SLGD_{today}.zip'
        logger.info('Downloading trade data')
        response = requests.get(link)
        with open(downloaded_slgd, 'wb') as fp:
            fp.write(response.content)

        logger.info('Unzip latest slgd into SLGD folder')
        with zipfile.ZipFile(downloaded_slgd, 'r') as fp:
            fp.extractall(dest_dir)

def edit_abb_file(abb_file, dest_dir):
    """
    Edit the input Amibroker batch file, fill in the actual ascii files paths
    downloaded from cafef.

    Raises
    ------
    ValueError
        Number of ascii files is not equal to number of ascii import actions
    """
    xml_tree = ET.parse(abb_file)
    steps = xml_tree.findall('.//Step')
    import_steps = list(filter(lambda x: x.find('.//Action').text == "ImportASCII", steps))
    ascii_files = list(Path(dest_dir).iterdir())
    # Guard that number of ascii files == number of ascii import actions
    if not len(import_steps) == len(ascii_files):
        raise ValueError('Number of ascii files is not equal to number of ascii import actions')
    for elem in zip(import_steps, ascii_files, strict=True):
        param = elem[0].find('.//Param')
        param.text = str(elem[1]).replace('\\', '\\\\')
        logger.debug(param.text)
    with open(abb_file, 'wb') as fp:
        xml_tree.write(fp)

def test_smthing(web_page):
    web_content = requests.get(web_page)
    soup = BeautifulSoup(web_content.text, features='html.parser')
    metastock_table = soup.find('table', {'class': 'metastock'})
    logger.info(metastock_table)


if __name__ == '__main__':
    logger = setup_logger()
    cafef_webpage, source_pattern, abb_file, dest_dir, amibroker = parse_user_config()
    logger.info(f'Start scrapping {cafef_webpage}')
    today = datetime.today().strftime(r'%d%m%Y')
    logger.debug(today)
    logger.debug(f'pattern to get source link: {source_pattern.format(today=today)}')
    trade_data_files_links = get_links(cafef_webpage, source_pattern.format(today=today))
    if trade_data_files_links:
        logger.info(f'Found the link to trade data for {today}!')
    else:
        logger.error(f'Cannot find link to trade data for {today}! Will try to fetch latest data from the web!')
        trade_data_files_links = get_links(cafef_webpage, source_pattern.format(today=r'[0-9]+'))
        trade_data_files_links = sorted(trade_data_files_links)[-1:]
        logger.debug(f'debug: {trade_data_files_links}')
    # From the found links, download the contents and unzip
    download_unzip(trade_data_files_links, dest_dir)
    # Edit the abb file of Amibroker then start the program
    edit_abb_file(abb_file, dest_dir)
    subprocess.run(amibroker)
