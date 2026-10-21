import sys
import codecs
import encodings
import io

assert sys.path == [EXPECTED_ARCHIVE]
assert sys.prefix == sys.base_prefix == sys.exec_prefix == sys.base_exec_prefix == EXPECTED_ROOT
assert sys.executable == EXPECTED_EXECUTABLE
assert sys.flags.isolated == 1 and sys.flags.ignore_environment == 1
assert sys.flags.safe_path and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
assert sys.flags.utf8_mode == 1 and sys.getfilesystemencoding() == 'utf-8'
assert sys.byteorder == 'little'
normalize = lambda path: path.replace('\\', '/')
assert normalize(encodings.__file__) == normalize(EXPECTED_ARCHIVE) + '/encodings/__init__.py'

for name in CODECS:
    module = __import__('encodings.' + name, fromlist=['getregentry'])
    assert normalize(module.__file__) == normalize(EXPECTED_ARCHIVE) + '/encodings/' + name + '.py'
    sample = VECTORS[name]['text']
    codec = module.getregentry()
    encoded = codec.encode(sample)[0]
    assert encoded.hex() == VECTORS[name]['hex']
    assert codec.decode(encoded)[0] == sample
    decoder = codec.incrementaldecoder()
    decoded = ''.join(decoder.decode(bytes([part])) for part in encoded) + decoder.decode(b'', True)
    assert decoded == sample
    encoder = codec.incrementalencoder()
    assert b''.join(encoder.encode(part) for part in sample) + encoder.encode('', True) == encoded
    stream = io.BytesIO()
    writer = codec.streamwriter(stream)
    writer.write(sample)
    stream.seek(0)
    assert codec.streamreader(stream).read() == sample

alias_count = 0
for alias, name in encodings.aliases.aliases.items():
    if name in CODECS:
        expected = __import__('encodings.' + name, fromlist=['getregentry']).getregentry().name
        assert codecs.lookup(alias).name == expected
        alias_count += 1

for name, invalid in [('ascii', b'\x80'), ('utf_8', b'\xff'), ('utf_8_sig', b'\xff'),
                      ('utf_16', b'\xff\xfe\x00'), ('utf_16_be', b'\x00'), ('utf_16_le', b'\x00'),
                      ('utf_32', b'\xff\xfe\x00\x00\x00'), ('utf_32_be', b'\x00\x11\x00\x00'),
                      ('utf_32_le', b'\x00\x00\x11\x00')]:
    codec = __import__('encodings.' + name, fromlist=['getregentry']).getregentry()
    try:
        codec.decode(invalid)
    except UnicodeError:
        pass
    else:
        raise AssertionError('Invalid input accepted by codec: ' + name)

for name in UNSUPPORTED_CODECS:
    try:
        codecs.lookup(name)
    except LookupError:
        pass
    else:
        raise AssertionError('Unselected codec found outside the owned ZIP: ' + name)

for name in ['syncwatch_poison', 'json', 'sitecustomize', 'usercustomize']:
    try:
        __import__(name)
    except ImportError:
        pass
    else:
        raise AssertionError('Unselected module found outside the owned ZIP: ' + name)

for name, module in list(sys.modules.items()):
    spec = getattr(module, '__spec__', None)
    origin = getattr(spec, 'origin', None)
    assert origin in (None, 'built-in', 'frozen') or normalize(origin).startswith(normalize(EXPECTED_ARCHIVE) + '/'), (name, origin)

print('SYNCWATCH_BOOTSTRAP_CODECS', len(CODECS), alias_count)
