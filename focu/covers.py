"""Source-attributed display images; never substitute unrelated stock imagery."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def image_url(value, base=''):
    if not isinstance(value,str) or not value.strip():
        return None
    result=urljoin(base,value.strip())
    p=urlsplit(result)
    if p.scheme!='https' or not p.hostname or p.username or p.password:
        return None
    return result


def source_cover(sources):
    for source in sources:
        url=image_url(source.get('image_url'),source.get('url',''))
        if url:
            return {'url':url,'source_url':source['url'],
                    'alt':source.get('image_alt') or source.get('title','Source image')}
    return None


class PostImages(HTMLParser):
    def __init__(self):
        super().__init__();self.images=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='img' and values.get('src'):
            self.images.append((values['src'],values.get('alt','')))


def feed_cover(entry,html,article_url):
    candidates=[]
    media='{http://search.yahoo.com/mrss/}'
    for tag in (media+'content',media+'thumbnail','enclosure','{http://www.w3.org/2005/Atom}link'):
        for node in entry.findall(tag):
            mime=node.get('type','')
            if tag.endswith('thumbnail') or mime.startswith('image/') or node.get('medium')=='image':
                candidates.append((node.get('url') or node.get('href'),node.get('title','')))
    parser=PostImages();parser.feed(html)
    candidates.extend(parser.images)
    for url,alt in candidates:
        safe=image_url(url,article_url)
        if safe:return {'image_url':safe,'image_alt':alt}
    return {}
