"""
Seed the FOSS corpus with representative code snippets for testing.
This simulates what would normally be populated from GitHub BigQuery + SPDX datasets.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Sample FOSS corpus data representing common patterns in GPL/LGPL/MIT code
CORPUS_DATA = [
    # GPL-2.0 examples
    {
        "source_repo": "linux/kernel",
        "source_file": "lib/sort.c",
        "license_spdx": "GPL-2.0-only",
        "language": "c",
        "code_snippet": """void sort(void *base, size_t num, size_t size,
    int (*cmp_func)(const void *, const void *),
    void (*swap_func)(void *, void *, int size))
{
    /* pre-scale counters for performance */
    int i = (num/2 - 1) * size, n = num * size, c, r;

    /* heapify */
    for ( ; i >= 0; i -= size) {
        for (r = i; r * 2 + size < n; r  = c) {
            c = r * 2 + size;
            if (c < n - size && cmp_func(base + c, base + c + size) < 0)
                c += size;
            if (cmp_func(base + r, base + c) >= 0)
                break;
            swap_func(base + r, base + c, size);
        }
    }

    /* sort */
    for (i = n - size; i > 0; i -= size) {
        swap_func(base, base + i, size);
        for (r = 0; r * 2 + size < i; r = c) {
            c = r * 2 + size;
            if (c < i - size && cmp_func(base + c, base + c + size) < 0)
                c += size;
            if (cmp_func(base + r, base + c) >= 0)
                break;
            swap_func(base + r, base + c, size);
        }
    }
}"""
    },
    {
        "source_repo": "gcc/gcc",
        "source_file": "libiberty/hashtab.c",
        "license_spdx": "GPL-2.0-or-later",
        "language": "c",
        "code_snippet": """static hashval_t
hash_pointer (const void *p)
{
  return (hashval_t) ((long)p >> 3);
}

static int
eq_pointer (const void *p1, const void *p2)
{
  return p1 == p2;
}

htab_t
htab_create (size_t size, htab_hash hash_f, htab_eq eq_f, htab_del del_f)
{
  htab_t result;

  result = (htab_t) xcalloc (1, sizeof (struct htab));
  *result = empty_htab;

  if (size < 3)
    size = 3;
  else
    size |= 1;

  result->size = size;
  result->hash_f = hash_f;
  result->eq_f = eq_f;
  result->del_f = del_f;
  result->entries = (void **) xcalloc (size, sizeof (void *));
  return result;
}"""
    },

    # GPL-3.0 examples
    {
        "source_repo": "python/cpython",
        "source_file": "Modules/_heapqmodule.c",
        "license_spdx": "GPL-3.0-only",
        "language": "python",
        "code_snippet": """def heappush(heap, item):
    \"\"\"Push item onto heap, maintaining the heap invariant.\"\"\"
    heap.append(item)
    _siftdown(heap, 0, len(heap)-1)

def heappop(heap):
    \"\"\"Pop the smallest item off the heap, maintaining the heap invariant.\"\"\"
    lastelt = heap.pop()    # raises appropriate IndexError if heap is empty
    if heap:
        returnitem = heap[0]
        heap[0] = lastelt
        _siftup(heap, 0)
        return returnitem
    return lastelt

def heapreplace(heap, item):
    \"\"\"Pop and return the current smallest value, and add the new item.
    This is more efficient than heappop() followed by heappush(), and can be
    more appropriate when using a fixed-size heap.  Note that the value
    returned may be larger than the item added.  Raises IndexError if the heap
    is empty.
    \"\"\"
    returnitem = heap[0]    # raises appropriate IndexError if heap is empty
    heap[0] = item
    _siftup(heap, 0)
    return returnitem"""
    },

    # AGPL-3.0 examples
    {
        "source_repo": "mongodb/mongo",
        "source_file": "src/mongo/base/string_map.h",
        "license_spdx": "AGPL-3.0-only",
        "language": "cpp",
        "code_snippet": """template <typename V>
class StringMap {
public:
    typedef std::unordered_map<std::string, V> MapType;
    typedef typename MapType::const_iterator const_iterator;
    typedef typename MapType::iterator iterator;
    typedef typename MapType::value_type value_type;

    StringMap() {}

    bool empty() const { return _map.empty(); }
    size_t size() const { return _map.size(); }
    void clear() { _map.clear(); }

    iterator find(StringData key) {
        auto it = _map.find(key.toString());
        return it;
    }

    const_iterator find(StringData key) const {
        auto it = _map.find(key.toString());
        return it;
    }

    V& operator[](StringData key) { return _map[key.toString()]; }

private:
    MapType _map;
};"""
    },

    # LGPL examples
    {
        "source_repo": "gnu/glibc",
        "source_file": "string/strcpy.c",
        "license_spdx": "LGPL-2.1-only",
        "language": "c",
        "code_snippet": """char *
strcpy (char *dest, const char *src)
{
  return memcpy (dest, src, strlen (src) + 1);
}

char *
strncpy (char *s1, const char *s2, size_t n)
{
  reg_char c;
  char *s = s1;

  while (n > 4)
    {
      c = *s2++;
      *s1++ = c;
      if (c == '\\0')
        {
          while (--n > 0)
            *s1++ = '\\0';
          return s;
        }
      c = *s2++;
      *s1++ = c;
      if (c == '\\0')
        {
          while (n > 2)
            {
              *s1++ = '\\0';
              --n;
            }
          return s;
        }
      n -= 4;
    }
  return s;
}"""
    },

    # MPL-2.0 examples
    {
        "source_repo": "mozilla/firefox",
        "source_file": "netwerk/base/nsURIHashKey.h",
        "license_spdx": "MPL-2.0",
        "language": "cpp",
        "code_snippet": """class nsURIHashKey : public PLDHashEntryHdr {
public:
    typedef nsIURI* KeyType;
    typedef const nsIURI* KeyTypePointer;

    explicit nsURIHashKey(const nsIURI* key) : mURI(const_cast<nsIURI*>(key)) {
        MOZ_COUNT_CTOR(nsURIHashKey);
    }
    nsURIHashKey(const nsURIHashKey& toCopy)
        : PLDHashEntryHdr(), mURI(toCopy.mURI) {
        MOZ_COUNT_CTOR(nsURIHashKey);
    }
    ~nsURIHashKey() { MOZ_COUNT_DTOR(nsURIHashKey); }

    nsIURI* GetKey() const { return mURI; }

    bool KeyEquals(const nsIURI* aKey) const {
        bool eq;
        if (NS_FAILED(mURI->Equals(aKey, &eq))) {
            return false;
        }
        return eq;
    }

    static const nsIURI* KeyToPointer(nsIURI* key) { return key; }
    static PLDHashNumber HashKey(const nsIURI* key) {
        nsAutoCString spec;
        if (key) {
            key->GetSpec(spec);
        }
        return mozilla::HashString(spec);
    }

    enum { ALLOW_MEMMOVE = false };

private:
    nsCOMPtr<nsIURI> mURI;
};"""
    },

    # MIT License examples
    {
        "source_repo": "expressjs/express",
        "source_file": "lib/router/index.js",
        "license_spdx": "MIT",
        "language": "javascript",
        "code_snippet": """function Router(options) {
  if (!(this instanceof Router)) {
    return new Router(options);
  }

  var opts = options || {};

  function router(req, res, next) {
    router.handle(req, res, next);
  }

  // mixin Router class functions
  Object.setPrototypeOf(router, proto);

  router.params = {};
  router._params = [];
  router.caseSensitive = opts.caseSensitive;
  router.mergeParams = opts.mergeParams;
  router.strict = opts.strict;
  router.stack = [];

  return router;
}"""
    },
    {
        "source_repo": "lodash/lodash",
        "source_file": "src/debounce.js",
        "license_spdx": "MIT",
        "language": "javascript",
        "code_snippet": """function debounce(func, wait, options) {
  let lastArgs,
    lastThis,
    maxWait,
    result,
    timerId,
    lastCallTime;

  let lastInvokeTime = 0;
  let leading = false;
  let maxing = false;
  let trailing = true;

  if (typeof func !== 'function') {
    throw new TypeError(FUNC_ERROR_TEXT);
  }
  wait = +wait || 0;
  if (isObject(options)) {
    leading = !!options.leading;
    maxing = 'maxWait' in options;
    maxWait = maxing ? Math.max(+options.maxWait || 0, wait) : maxWait;
    trailing = 'trailing' in options ? !!options.trailing : trailing;
  }

  function invokeFunc(time) {
    const args = lastArgs;
    const thisArg = lastThis;
    lastArgs = lastThis = undefined;
    lastInvokeTime = time;
    result = func.apply(thisArg, args);
    return result;
  }

  return debounced;
}"""
    },

    # Apache-2.0 examples
    {
        "source_repo": "apache/kafka",
        "source_file": "clients/src/main/java/org/apache/kafka/common/utils/Utils.java",
        "license_spdx": "Apache-2.0",
        "language": "java",
        "code_snippet": """public static int murmur2(final byte[] data) {
    int length = data.length;
    int seed = 0x9747b28c;
    // 'm' and 'r' are mixing constants generated offline.
    // They're not really 'magic', they just happen to work well.
    final int m = 0x5bd1e995;
    final int r = 24;

    // Initialize the hash to a random value
    int h = seed ^ length;
    int length4 = length / 4;

    for (int i = 0; i < length4; i++) {
        final int i4 = i * 4;
        int k = (data[i4 + 0] & 0xff) + ((data[i4 + 1] & 0xff) << 8) + ((data[i4 + 2] & 0xff) << 16) + ((data[i4 + 3] & 0xff) << 24);
        k *= m;
        k ^= k >>> r;
        k *= m;
        h *= m;
        h ^= k;
    }

    switch (length % 4) {
        case 3: h ^= (data[(length & ~3) + 2] & 0xff) << 16;
        case 2: h ^= (data[(length & ~3) + 1] & 0xff) << 8;
        case 1: h ^= data[length & ~3] & 0xff;
            h *= m;
    }

    h ^= h >>> 13;
    h *= m;
    h ^= h >>> 15;

    return h;
}"""
    },

    # BSD-3-Clause examples
    {
        "source_repo": "freebsd/freebsd",
        "source_file": "lib/libc/string/memmove.c",
        "license_spdx": "BSD-3-Clause",
        "language": "c",
        "code_snippet": """void *
memmove(void *dst, const void *src, size_t len)
{
    size_t i;

    /*
     * If the buffers don't overlap, it doesn't matter what direction
     * we copy in. If they do, it does matter. If the destination buffer
     * is at a lower address than the source buffer, we copy from bottom
     * to top. If the destination buffer is at a higher address than the
     * source buffer, we copy from top to bottom.
     */
    if ((uintptr_t)dst < (uintptr_t)src) {
        /*
         * As long as the sizes are at least sizeof(word), do word-sized
         * copies.  The destination alignment may start off as not
         * word-aligned, but we copy one byte at a time until it is
         * word-aligned.
         */
        for (i = 0; i < len; i++)
            ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
    } else {
        /*
         * Copy from top to bottom.
         */
        if (len != 0) {
            i = len;
            do {
                i--;
                ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
            } while (i != 0);
        }
    }
    return (dst);
}"""
    },

    # Python binary search (classic algorithm - often AI-generated)
    {
        "source_repo": "python/cpython",
        "source_file": "Lib/bisect.py",
        "license_spdx": "PSF-2.0",
        "language": "python",
        "code_snippet": """def bisect_right(a, x, lo=0, hi=None, *, key=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    if key is None:
        while lo < hi:
            mid = (lo + hi) // 2
            if x < a[mid]:
                hi = mid
            else:
                lo = mid + 1
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            if x < key(a[mid]):
                hi = mid
            else:
                lo = mid + 1
    return lo

def bisect_left(a, x, lo=0, hi=None, *, key=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    if key is None:
        while lo < hi:
            mid = (lo + hi) // 2
            if a[mid] < x:
                lo = mid + 1
            else:
                hi = mid
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            if key(a[mid]) < x:
                lo = mid + 1
            else:
                hi = mid
    return lo"""
    },
]


def seed_database():
    """Seed the database with corpus snippets."""
    db = SessionLocal()

    try:
        from app.models import CorpusSnippet
        existing = db.query(CorpusSnippet).count()
        if existing > 0:
            logger.info(f"Corpus already has {existing} snippets. Skipping seed.")
            return

        logger.info(f"Seeding corpus with {len(CORPUS_DATA)} snippets...")

        for i, data in enumerate(CORPUS_DATA):
            logger.info(f"Adding snippet {i+1}/{len(CORPUS_DATA)}: {data['source_repo']}/{data['source_file']}")

            from app.detector import tokenize_code, compute_minhash, compute_embedding
            from app.license_taxonomy import classify_license
            import uuid

            risk_tier, _ = classify_license(data['license_spdx'])
            tokens = tokenize_code(data['code_snippet'], data.get('language'))
            minhash = compute_minhash(tokens)
            embedding = compute_embedding(data['code_snippet'])

            snippet = CorpusSnippet(
                id=str(uuid.uuid4()),
                source_repo=data['source_repo'],
                source_file=data['source_file'],
                license_spdx=data['license_spdx'],
                license_risk_tier=risk_tier,
                language=data.get('language'),
                code_snippet=data['code_snippet'],
                ast_tokens={"tokens": tokens[:100]},
                minhash_signature=minhash,
                embedding=embedding,
            )
            db.add(snippet)

        db.commit()
        logger.info(f"✅ Corpus seeded successfully with {len(CORPUS_DATA)} snippets")

    except Exception as e:
        logger.error(f"Failed to seed corpus: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()