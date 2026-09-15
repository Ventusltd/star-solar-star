# RFC 8785 serializer

`rfc8785.py` is the unchanged `_impl.py` from Trail of Bits rfc8785.py v0.1.4:
https://github.com/trailofbits/rfc8785.py/tree/v0.1.4

The Apache 2.0 license is in `RFC8785-LICENSE`. The implementation credits
Andrew Rundgren's reference implementation for adapted portions. Vendoring
keeps proposal validation independent of package installation and network access.
The application additionally rejects all integer-valued numbers outside the
JavaScript safe integer range, including floats, on both runtimes.
