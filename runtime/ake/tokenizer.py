"""Tokenizer (Stage 8) — the lexical front-end. ONE responsibility: raw text -> ordered tokens.

It does NOT resolve entities/attributes/relations, infer operations, classify grammar, build
intent, plan, or execute. Those all have owners. The tokenizer only splits text into tokens and
keeps multi-word phrases together when the vocabulary says those adjacent words form a known
phrase (e.g. "Order Items", "total_amount", "Purchase Order Line").

Read-only vocabulary use: the tokenizer consults the Vocabulary Registry ONLY to decide "should
these adjacent words stay together as one token?" — never to resolve meaning. It never learns; the
Vocabulary Registry learns, the tokenizer just consumes the latest vocabulary. If a new workbook
adds a phrase, the tokenizer preserves it automatically because it is in the vocabulary — no code
change.

Workbook-independent: no hardcoded entity/column names, no workbook logic. Every phrase it
preserves comes from the live vocabulary.

Each token carries: text (original), norm (normalized), start, end (character offsets).
"""


class Token:
    __slots__ = ("text", "norm", "start", "end")

    def __init__(self, text, norm, start, end):
        self.text = text
        self.norm = norm
        self.start = start
        self.end = end

    def as_dict(self):
        return {"text": self.text, "norm": self.norm, "start": self.start, "end": self.end}

    def __repr__(self):
        return "Token(%r @%d:%d)" % (self.text, self.start, self.end)


class Tokenizer:
    """Lexical tokenizer. Splits on whitespace, then greedily merges adjacent words into a single
    token when the merged phrase exists in the vocabulary. Purely lexical; no interpretation."""

    def __init__(self, vocabulary=None, max_phrase_len=5):
        # vocabulary: object with candidates(word) or resolve(word); consulted read-only only to
        # test phrase existence. Optional — without it the tokenizer degrades to word splitting.
        self.vocabulary = vocabulary
        self.max_phrase_len = max_phrase_len

    def _norm(self, s):
        # normalization is lexical only: lowercase + collapse internal spaces. NOT stemming, NOT
        # synonym expansion (that is vocabulary/resolver territory).
        return " ".join(s.lower().split())

    def _phrase_known(self, phrase):
        """Read-only vocabulary check via a SINGLE meaning-free API: does this phrase exist as a
        known vocabulary word? The tokenizer asks only 'keep these words together?' and never sees
        candidates, canonicals, types, or which underlying vocabulary (universal vs workbook)
        backs it — that abstraction stays behind phrase_exists()."""
        v = self.vocabulary
        if v is None or not hasattr(v, "phrase_exists"):
            return False
        return bool(v.phrase_exists(self._norm(phrase)))

    def _raw_words(self, text):
        """Split into (word, start, end) triples on whitespace, keeping offsets. Trailing '?' is
        dropped as a separator but offsets of real words are preserved."""
        words = []
        i, n = 0, len(text)
        while i < n:
            if text[i].isspace() or text[i] == "?":
                i += 1
                continue
            j = i
            while j < n and not text[j].isspace() and text[j] != "?":
                j += 1
            words.append((text[i:j], i, j))
            i = j
        return words

    def tokenize(self, text):
        """Raw text -> ordered list[Token]. Multi-word phrases known to the vocabulary are kept as
        one token (greedy longest-match, up to max_phrase_len words). Everything else is a
        single-word token. Offsets always preserved."""
        text = str(text)
        words = self._raw_words(text)
        tokens = []
        i = 0
        while i < len(words):
            # greedy longest phrase: try the longest window first, shrink until a known phrase or 1
            matched = None
            hi = min(len(words), i + self.max_phrase_len)
            for end in range(hi, i + 1, -1):          # end from longest window down to i+2 (>=2 words)
                span_words = words[i:end]
                phrase = " ".join(w for w, _, _ in span_words)
                if self._phrase_known(phrase):
                    start_off = span_words[0][1]
                    end_off = span_words[-1][2]
                    matched = Token(text[start_off:end_off], self._norm(phrase), start_off, end_off)
                    i = end
                    break
            if matched is None:
                w, s, e = words[i]
                tokens.append(Token(w, self._norm(w), s, e))
                i += 1
            else:
                tokens.append(matched)
        return tokens

    def tokens(self, text):
        """Convenience: just the normalized token strings, in order."""
        return [t.norm for t in self.tokenize(text)]
