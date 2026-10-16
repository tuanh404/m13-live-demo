import hashlib
import io
import json

import httpx
import pytest
from PIL import Image

from src.data.bdd_subset import acquire


def test_pinned_subset_checks_hash_dimensions_resume_and_identity(tmp_path):
    image_id = '12345678-abcdef01'
    selection = tmp_path / 'selection.json'
    selection.write_text(json.dumps({'demo_image_ids': [image_id], 'pilot_image_ids': []}))
    buf = io.BytesIO()
    Image.new('RGB', (1280, 720), 'gray').save(buf, format='JPEG')
    jpeg = buf.getvalue()
    sha = hashlib.sha256(jpeg).hexdigest()
    calls = []

    def serve(request):
        calls.append(request.url.path)
        if '/resolve/' in request.url.path:
            return httpx.Response(200, content=jpeg)
        if request.url.path.endswith('/val'):
            return httpx.Response(200, json=[{'type': 'directory', 'path': 'images/100k/val/val_001'}])
        return httpx.Response(200, json=[{'type': 'file', 'path': f'images/100k/val/val_001/{image_id}.jpg',
                                         'size': len(jpeg), 'lfs': {'oid': sha}}])
    client = httpx.Client(transport=httpx.MockTransport(serve))
    output = tmp_path / 'photos'
    result = acquire(selection, output, 'a'*40, client=client)
    assert result['images'] == 1 and result['complete']
    acquire(selection, output, 'a'*40, client=client)
    assert len([p for p in calls if '/resolve/' in p]) == 1
    assert not json.loads((output / 'acquisition.json').read_text())['official_image_hashes_available']
    (output / (image_id + '.jpg')).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash'):
        acquire(selection, output, 'a'*40, client=client)
    assert (output / (image_id + '.jpg')).read_bytes() == b'tampered'
    with pytest.raises(ValueError, match='lượt tải khác'):
        acquire(selection, output, 'b'*40, client=client)
