# coding: utf-8
from __future__ import unicode_literals

import re
import json
import itertools

from .common import InfoExtractor

from ..compat import (
    compat_str,
    compat_urllib_request,
)
from ..utils import (
    ExtractorError,
    int_or_none,
    orderedSet,
    str_to_int,
    unescapeHTML,
)


class DailymotionBaseInfoExtractor(InfoExtractor):
    @staticmethod
    def _build_request(url):
        """Build a request with the family filter disabled"""
        request = compat_urllib_request.Request(url)
        request.add_header('Cookie', 'family_filter=off; ff=off')
        return request


class DailymotionIE(DailymotionBaseInfoExtractor):
    """Information Extractor for Dailymotion"""

    _VALID_URL = r'(?i)(?:https?://)?(?:(www|touch)\.)?dailymotion\.[a-z]{2,3}/(?:(embed|#)/)?video/(?P<id>[^/?_]+)'
    IE_NAME = 'dailymotion'

    _FORMATS = [
        ('stream_h264_ld_url', 'ld'),
        ('stream_h264_url', 'standard'),
        ('stream_h264_hq_url', 'hq'),
        ('stream_h264_hd_url', 'hd'),
        ('stream_h264_hd1080_url', 'hd180'),
    ]

    _TESTS = [
        {
            'url': 'https://www.dailymotion.com/video/x2iuewm_steam-machine-models-pricing-listed-on-steam-store-ign-news_videogames',
            'md5': '2137c41a8e78554bb09225b8eb322406',
            'info_dict': {
                'id': 'x2iuewm',
                'ext': 'mp4',
                'uploader': 'IGN',
                'title': 'Steam Machine Models, Pricing Listed on Steam Store - IGN News',
                'upload_date': '20150306',
                'duration': 74,
            }
        },
        # Vevo video
        {
            'url': 'http://www.dailymotion.com/video/x149uew_katy-perry-roar-official_musi',
            'info_dict': {
                'title': 'Roar (Official)',
                'id': 'USUV71301934',
                'ext': 'mp4',
                'uploader': 'Katy Perry',
                'upload_date': '20130905',
            },
            'params': {
                'skip_download': True,
            },
            'skip': 'VEVO is only available in some countries',
        },
        # age-restricted video
        {
            'url': 'http://www.dailymotion.com/video/xyh2zz_leanna-decker-cyber-girl-of-the-year-desires-nude-playboy-plus_redband',
            'md5': '0d667a7b9cebecc3c89ee93099c4159d',
            'info_dict': {
                'id': 'xyh2zz',
                'ext': 'mp4',
                'title': 'Leanna Decker - Cyber Girl Of The Year Desires Nude [Playboy Plus]',
                'uploader': 'HotWaves1012',
                'age_limit': 18,
            }
        }
    ]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        url = 'https://www.dailymotion.com/video/%s' % video_id

        # Retrieve video webpage to extract further information
        request = self._build_request(url)
        webpage = self._download_webpage(request, video_id)

        # Extract URL, uploader and title from webpage
        self.report_extraction(video_id)

        # It may just embed a vevo video:
        m_vevo = re.search(
            r'<link rel="video_src" href="[^"]*?vevo.com[^"]*?video=(?P<id>[\w]*)',
            webpage)
        if m_vevo is not None:
            vevo_id = m_vevo.group('id')
            self.to_screen('Vevo video detected: %s' % vevo_id)
            return self.url_result('vevo:%s' % vevo_id, ie='Vevo')

        age_limit = self._rta_search(webpage)

        video_upload_date = None
        mobj = re.search(r'<meta property="video:release_date" content="([0-9]{4})-([0-9]{2})-([0-9]{2}).+?"/>', webpage)
        if mobj is not None:
            video_upload_date = mobj.group(1) + mobj.group(2) + mobj.group(3)

        embed_url = 'https://www.dailymotion.com/embed/video/%s' % video_id
        embed_request = self._build_request(embed_url)
        embed_page = self._download_webpage(
            embed_request, video_id, 'Downloading embed page')
        info = self._search_regex(r'var info = ({.*?}),$', embed_page,
                                  'video info', flags=re.MULTILINE)
        info = json.loads(info)
        if info.get('error') is not None:
            msg = 'Couldn\'t get video, Dailymotion says: %s' % info['error']['title']
            raise ExtractorError(msg, expected=True)

        formats = []
        for (key, format_id) in self._FORMATS:
            video_url = info.get(key)
            if video_url is not None:
                m_size = re.search(r'H264-(\d+)x(\d+)', video_url)
                if m_size is not None:
                    width, height = map(int_or_none, (m_size.group(1), m_size.group(2)))
                else:
                    width, height = None, None
                formats.append({
                    'url': video_url,
                    'ext': 'mp4',
                    'format_id': format_id,
                    'width': width,
                    'height': height,
                })
        if not formats:
            raise ExtractorError('Unable to extract video URL')

        # subtitles
        video_subtitles = self.extract_subtitles(video_id, webpage)

        view_count = str_to_int(self._search_regex(
            r'video_views_count[^>]+>\s+([\d\.,]+)',
            webpage, 'view count', fatal=False))

        title = self._og_search_title(webpage, default=None)
        if title is None:
            title = self._html_search_regex(
                r'(?s)<span\s+id="video_title"[^>]*>(.*?)</span>', webpage,
                'title')

        return {
            'id': video_id,
            'formats': formats,
            'uploader': info['owner.screenname'],
            'upload_date': video_upload_date,
            'title': title,
            'subtitles': video_subtitles,
            'thumbnail': info['thumbnail_url'],
            'age_limit': age_limit,
            'view_count': view_count,
            'duration': info['duration']
        }

    def _get_subtitles(self, video_id, webpage):
        try:
            sub_list = self._download_webpage(
                'https://api.dailymotion.com/video/%s/subtitles?fields=id,language,url' % video_id,
                video_id, note=False)
        except ExtractorError as err:
            self._downloader.report_warning('unable to download video subtitles: %s' % compat_str(err))
            return {}
        info = json.loads(sub_list)
        if (info['total'] > 0):
            sub_lang_list = dict((l['language'], [{'url': l['url'], 'ext': 'srt'}]) for l in info['list'])
            return sub_lang_list
        self._downloader.report_warning('video doesn\'t have subtitles')
        return {}


class DailymotionPlaylistIE(DailymotionBaseInfoExtractor):
    IE_NAME = 'dailymotion:playlist'
    _VALID_URL = r'(?:https?://)?(?:www\.)?dailymotion\.[a-z]{2,3}/playlist/(?P<id>.+?)/'
    _MORE_PAGES_INDICATOR = r'(?s)<div class="pages[^"]*">.*?<a\s+class="[^"]*?icon-arrow_right[^"]*?"'
    _PAGE_TEMPLATE = 'https://www.dailymotion.com/playlist/%s/%s'
    _TESTS = [{
        'url': 'http://www.dailymotion.com/playlist/xv4bw_nqtv_sport/1#video=xl8v3q',
        'info_dict': {
            'title': 'SPORT',
            'id': 'xv4bw_nqtv_sport',
        },
        'playlist_mincount': 20,
    }]

    def _extract_entries(self, id):
        video_ids = []
        for pagenum in itertools.count(1):
            request = self._build_request(self._PAGE_TEMPLATE % (id, pagenum))
            webpage = self._download_webpage(request,
                                             id, 'Downloading page %s' % pagenum)

            video_ids.extend(re.findall(r'data-xid="(.+?)"', webpage))

            if re.search(self._MORE_PAGES_INDICATOR, webpage) is None:
                break
        return [self.url_result('http://www.dailymotion.com/video/%s' % video_id, 'Dailymotion')
                for video_id in orderedSet(video_ids)]

    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('id')
        webpage = self._download_webpage(url, playlist_id)

        return {
            '_type': 'playlist',
            'id': playlist_id,
            'title': self._og_search_title(webpage),
            'entries': self._extract_entries(playlist_id),
        }


class DailymotionUserIE(DailymotionPlaylistIE):
    IE_NAME = 'dailymotion:user'
    _VALID_URL = r'https?://(?:www\.)?dailymotion\.[a-z]{2,3}/(?:(?:old/)?user/)?(?P<user>[^/]+)$'
    _PAGE_TEMPLATE = 'http://www.dailymotion.com/user/%s/%s'
    _TESTS = [{
        'url': 'https://www.dailymotion.com/user/nqtv',
        'info_dict': {
            'id': 'nqtv',
            'title': 'Rémi Gaillard',
        },
        'playlist_mincount': 100,
    }]

    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)
        user = mobj.group('user')
        webpage = self._download_webpage(
            'https://www.dailymotion.com/user/%s' % user, user)
        full_user = unescapeHTML(self._html_search_regex(
            r'<a class="nav-image" title="([^"]+)" href="/%s">' % re.escape(user),
            webpage, 'user'))

        return {
            '_type': 'playlist',
            'id': user,
            'title': full_user,
            'entries': self._extract_entries(user),
        }


class DailymotionCloudIE(DailymotionBaseInfoExtractor):
    _VALID_URL_PREFIX = r'http://api\.dmcloud\.net/(?:player/)?embed/'
    _VALID_URL = r'%s[^/]+/(?P<id>[^/?]+)' % _VALID_URL_PREFIX
    _VALID_EMBED_URL = r'%s[^/]+/[^\'"]+' % _VALID_URL_PREFIX

    _TESTS = [{
        # From http://www.francetvinfo.fr/economie/entreprises/les-entreprises-familiales-le-secret-de-la-reussite_933271.html
        # Tested at FranceTvInfo_2
        'url': 'http://api.dmcloud.net/embed/4e7343f894a6f677b10006b4/556e03339473995ee145930c?auth=1464865870-0-jyhsm84b-ead4c701fb750cf9367bf4447167a3db&autoplay=1',
        'only_matching': True,
    }, {
        # http://www.francetvinfo.fr/societe/larguez-les-amarres-le-cobaturage-se-developpe_980101.html
        'url': 'http://api.dmcloud.net/player/embed/4e7343f894a6f677b10006b4/559545469473996d31429f06?auth=1467430263-0-90tglw2l-a3a4b64ed41efe48d7fccad85b8b8fda&autoplay=1',
        'only_matching': True,
    }]

    @classmethod
    def _extract_dmcloud_url(self, webpage):
        mobj = re.search(r'<iframe[^>]+src=[\'"](%s)[\'"]' % self._VALID_EMBED_URL, webpage)
        if mobj:
            return mobj.group(1)

        mobj = re.search(
            r'<input[^>]+id=[\'"]dmcloudUrlEmissionSelect[\'"][^>]+value=[\'"](%s)[\'"]' % self._VALID_EMBED_URL,
            webpage)
        if mobj:
            return mobj.group(1)

    def _real_extract(self, url):
        video_id = self._match_id(url)

        request = self._build_request(url)
        webpage = self._download_webpage(request, video_id)

        title = self._html_search_regex(r'<title>([^>]+)</title>', webpage, 'title')

        video_info = self._parse_json(self._search_regex(
            r'var\s+info\s*=\s*([^;]+);', webpage, 'video info'), video_id)

        # TODO: parse ios_url, which is in fact a manifest
        video_url = video_info['mp4_url']

        return {
            'id': video_id,
            'url': video_url,
            'title': title,
            'thumbnail': video_info.get('thumbnail_url'),
        }
