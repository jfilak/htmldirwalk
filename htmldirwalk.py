import os
import logging

import requests

from collections import deque
from html.parser import HTMLParser


class LinkHtmlParser(HTMLParser):

    def __init__(self):
        super(LinkHtmlParser, self).__init__()

        self._listing_content = False
        self._href = None
        self.links = list()

    def handle_starttag(self, tag, attrs):
        self._href = None

        logging.debug('Start {}'.format(tag))
        if not self._listing_content:
            self._listing_content = tag == 'hr'

        if not self._listing_content:
            return

        if not tag in ('a', 'A'):
            return

        self._href = next((value for attr, value in attrs if attr == 'href'), None)

    def handle_endtag(self, tag):
        if tag in ('a', 'A'):
            self._href = None

    def handle_data(self, data):
        if not self._href:
            return

        logging.debug('Handling {}'.format(data))
        if data != 'Parent Directory':
            logging.debug('Adding {}'.format(self._href))
            self.links.append(self._href)


class OpenStackObjecStoreParser(HTMLParser):

    def __init__(self):
        super(OpenStackObjecStoreParser, self).__init__()

        self._listing_content = False
        self._item = False
        self.links = list()

    def handle_starttag(self, tag, attrs):
        logging.debug('Start {}'.format(tag))

        if tag == 'table':
            self._listing_content = next((value for attr, value in attrs if attr == 'id'), None) is not None

        if not self._listing_content:
            return

        if tag == 'tr':
            for attr, value in attrs:
                logging.debug('Attr {}: {}'.format(attr, value))

                if attr != 'class':
                    continue

                classes = value.split(' ')

                if 'item' not in classes:
                    logging.debug('tr :: not item')
                    continue

                if 'subdir' in classes:
                    logging.debug('tr :: subdir')
                    self._item = True
                    break

                if 'type-application' in classes and 'type-directory' not in classes:
                    logging.debug('tr :: file')
                    self._item = True
                    break

        if not self._item:
            logging.debug('not td')
            return

        if tag == 'td':
            self._item_name = next((value for attr, value in attrs if attr == 'class'), None) == 'colname'

        if not self._item_name:
           logging.debug('not file name')
           return

        if tag != 'a':
            logging.debug('not reference')
            return

        href = next((value for attr, value in attrs if attr == 'href'), None)
        logging.debug('add link %s', href)
        self.links.append(href)

    def handle_endtag(self, tag):
        if tag == 'td':
            self._item_name = False

        if tag == 'tr':
            self._item = False

        if tag == 'table':
            self._listing_content = False

    def handle_data(self, data):
        pass


class HtmlDirWalker(object):

    def __init__(self):
        self._logger = logging.getLogger()

        self._http = requests
        self._parser = LinkHtmlParser
        self._max_depth = 0

    def set_logger(self, logger):
        self._logger = logger
        return self

    def set_http_worker(self, worker):
        self._http = worker
        return self

    def set_html_parser(self, parser):
        self._parser = parser
        return self

    def set_max_depth(self, max_depth):
        self._max_depth = max_depth
        return self

    def _download(self, url):
        self._logger.debug('Downloading {}'.format(url))
        r = self._http.get(url)

        if r.status_code >= 400:
            raise RuntimeError('Cannot get {}: status {}'.format(url, r.status_code))

        return r.text

    def _parse(self, text):
        logging.debug('Parsing ...')

        html_parser = self._parser()
        html_parser.feed(text)

        return html_parser.links

    def _directory_contents(self, url):
        page = self._download(url)
        links = self._parse(page)

        dirs = list()
        files = list()
        for ref in links:
            if ref[-1] == '/':
                dirs.append(ref)
            else:
                files.append(ref)

        return (dirs, files)

    def walk(self, url):
        dirs = deque((('', 1), ))

        while dirs:
            root, depth = dirs.pop()

            content = self._directory_contents(os.path.join(url, root))

            if self._max_depth == 0 or depth < self._max_depth:
                dirs.extendleft(((os.path.join(root, d), depth+1) for d in content[0]))

            yield (root, content[0], content[1])
