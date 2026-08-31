Changelog
=========

1.19.0 (unreleased)
-------------------

- [fix] Give the ``max_alloc_bytes`` estimate a depth term, so a 1-bit document
  can no longer allocate eight times its budget (#737). ``check_pixel_size()``
  sizes an allocation at ``width * height * channels * 4``, but at depth 1
  ``numpy_io._parse_array()`` unpacks the buffer with ``np.unpackbits`` -- one
  float32 per *bit* -- so the array follows the byte count the codec returns
  rather than the pixel count. The two disagree eightfold: ``decompress()``'s
  ``length`` is one byte per pixel at depth 1, where a row of ``width`` pixels
  packs into ``width // 8``, and a body written that wide is returned in full
  because the length check is skipped below depth 8. A 64x64 1-bit document
  therefore returned ``(64, 64, 8)``, 131,072 bytes, against a 16,384-byte
  estimate, and the guard admitted it -- a gap in a security control
  (GHSA-8q6g-vjhf-jp8m) whose whole job is to bound the allocation before it
  happens.

  The estimate now asks the codec, through the new
  :py:func:`psd_tools.compression.decompressed_size_bound`, rather than
  multiplying by a flat eight. A properly packed body -- what
  ``colormodes/4x4_1bit_bitmap.psd`` and any document Photoshop writes carries
  -- still allocates only the planes it really occupies, where a flat factor
  would have rejected that fixture at four times its size. ZIP is the one codec
  whose inflated size cannot be known without inflating it, so a conforming
  1-bit ZIP body is now bounded at eight times its allocation. Nothing in
  practice pays for that: of the 293 documents in ``tests/psd_files``, 241 store
  their merged image data RLE and 52 RAW, and none uses either ZIP codec --
  which is where the layer channels do use ZIP, and where this bound is not
  consulted.

  ``_safe_zlib_decompress()`` also now enforces the ceiling it documents. It
  probes one byte past the limit to catch an oversize stream, and a stream
  inflating to exactly that was handed back a byte over -- eight more float32
  values at depth 1 than any arithmetic over ``length`` could account for. Such
  a channel is now refused: degraded to black from depth 8 up, where it used to
  raise a length mismatch instead, and ending the read below depth 8, as every
  undecodable 1-bit channel already did.

- [fix] Replace a failed channel with exactly the byte count it declares, at
  every depth (#737). The black fill substituted for an undecodable channel was
  a PIL image whose mode was picked from the depth -- ``"L"`` for 8, ``"RGBA"``
  for anything else -- so depth 16 came back at four bytes per pixel against a
  declared two, and every reader downstream saw the channels at twice their
  width. A 4x4 RGB document whose merged image data fails to decode read
  ``(4, 4, 6)`` instead of ``(4, 4, 3)`` -- ``ImageData.get_data()``
  decompresses every channel in one call, so that section fails as a unit -- and
  allocated twice what the guard had estimated. The same substitute serves the
  per-channel readers, ``ChannelData.get_data()`` for layers and the pattern
  reader, so a failed 16-bit channel there came back double-width too. Depths 8
  and 32 are unaffected, their modes having happened to match.

- [fix] Split a pattern's alpha off by its slot layout rather than by its
  colour mode, so a multichannel-mode pattern composites instead of raising
  (#741). The split was keyed on ``EXPECTED_CHANNELS``, whose multichannel
  entry is 64 -- the format's maximum number of channels, not any pattern's own
  count. ``shape[2] > 64`` is never true, so the alpha stayed in the colour
  array and the too-wide result was rejected downstream: ``AssertionError:
  source has 4 channels, expected 1 or 3`` on a pattern fill layer, and
  ``AssertionError: Inconsistent pattern channels.`` on a pattern overlay
  effect. A pattern reserves ``len(channels) - 2`` colour slots and writes its
  transparency into the last of the remaining two, which is the pattern's own
  statement of where its boundary lies rather than a mode's.

  Multichannel is the mode that can never reach its constant, but it is not the
  only one that missed the split: the mode's count is the document's, not the
  pattern's, so a pattern storing fewer colour planes than its mode's
  constant -- an indexed or RGB one carrying a single colour plane and an
  alpha -- kept its alpha in the colour array as well. Rendering is byte-for-byte
  unchanged for every pattern layout in the test corpus and in the patterns
  Photoshop ships.

- [fix] Convert a CMYK fill descriptor through ink space, so it no longer
  renders black on every non-CMYK document (#763, #765). ``_get_cmyk()`` read the
  descriptor into the compositor's canvas convention, where 1.0 is *no* ink,
  and then handed that to :py:func:`psd_tools.color_convert.cmyk_to_rgb`, whose
  contract is ink space, where 0.0 is no ink. The flip was never undone, so on
  an RGB, indexed, grayscale, bitmap, duotone, multichannel or Lab document
  every colour arrived as its own opposite and collapsed: white ``C0 M0 Y0 K0``
  rendered ``(0, 0, 0)``, and so did cyan, magenta and yellow. Black was the
  one colour that came out right, by coincidence. This is the same confusion as
  #747 on the opposite leg; a CMYK document was never affected.

- [fix] Clamp a fill descriptor's colour components so an out-of-range value
  saturates instead of corrupting the render (#757, #764). Nothing in the format
  constrains a component to the range its colour class normalizes by, so a
  writer emitting ``Rd = 300`` or ``Gry = 150`` produces a value outside
  ``[0, 1]``.

  A flat opaque fill was shielded from this, because the compositor clips its
  own arrays before the uint8 cast. What was not shielded is anything that
  blends the value first -- a layer effect, a partial alpha, an anti-aliased
  vector edge -- because the clip then runs on arithmetic that is already
  wrong. A shape whose fill descriptor carries a beyond-black grey rendered
  white pixels along its stroke, and a beyond-red ``HSBC`` rendered bright
  cyan ones, where the stroke colour was dark grey.

  All five colour classes are now guarded where the untrusted number enters, as
  Lab already was since #743, so ``color_convert``'s documented ``[0, 1]``
  input contracts stay unchanged. The colour-noise gradient's RGB path is
  guarded too, since its bands come from raw ``"Mnm "``/``"Mxm "`` values. Hue is
  excluded on purpose: it is an angle, so it still wraps.

  :py:func:`psd_tools.color_convert.hsb_to_rgb` is now total, matching
  :py:func:`~psd_tools.color_convert.lab_to_rgb`. Its documented ``[0, 1]``
  result previously held only for in-range saturation and brightness, and a NaN
  saturation propagated to the caller.

- [fix] Read a 32-bit document with transparency through
  :py:meth:`~psd_tools.api.psd_image.PSDImage.numpy`, which raised
  ``ValueError: assignment destination is read-only``. Photoshop writes 32-bit
  RGB with a transparency channel routinely, so this was an ordinary file
  shape rather than a malformed one, and
  :py:func:`psd_tools.composite.composite` failed with it for the same reason.
  ``topil()`` was unaffected, and ``PSDImage.composite()`` only appeared to be
  because it short-circuits to the stored preview.

  ``_parse_array()`` rescales at depths 1, 8 and 16, and the conversion that
  needs hands back a fresh, writeable, native-endian array. Depth 32 needs no
  rescaling, so it returned ``np.frombuffer()``'s view of the file's bytes --
  read-only, and still big-endian where every other depth returns
  ``np.float32``. Un-premultiplying the preview writes in place, and it runs
  only for RGB with transparency, which is why just that one combination
  raised. All four depths now return the same kind of array. The cost is one
  more array the size of the merged image data on 32-bit documents, which is
  what the other three depths already allocate (#738).

- [fix] Convert a scalar backdrop instead of broadcasting it across every
  channel. ``composite()`` accepts its backdrop as a scalar, a per-channel
  sequence or a full array. #722, in this same release, taught the
  single-channel *array* spelling to go through the colour mode's conversion,
  but the scalar path was missed and stayed on ``np.full()`` -- so the same
  backdrop had two answers depending on how it was written. A scalar now takes
  the same conversion, and only a genuinely single component is converted: a
  per-channel sequence is left exactly as given. Both halves land together, so
  no released version carries the split; what *is* longstanding is the colour
  below, which every released version got wrong by broadcasting either
  spelling.

  On a **Lab** document this was the default backdrop. ``color=1.0`` put both
  chroma axes at byte 255 -- the extreme corner of each -- so a document
  composited against maximum chroma at maximum lightness where white is
  ``(255, 128, 128)``. On a **CMYK** document the default is unaffected, since
  ``1.0`` is white either way, but other scalars were the over-inked build that
  widening exists to avoid: ``color=0.0`` broadcast to ``(0, 0, 0, 0)``, every
  plate at 100%. RGB, grayscale, indexed and multichannel are unchanged --
  replication is the conversion there (#753).

- [fix] Stop ``composite()`` shifting both chroma planes of a Lab document.
  The result was built with ``Image.fromarray(pixels, "LAB")``, and PIL's
  ``"LAB"`` unpacker reads the two chroma planes as *signed* and adds 128 --
  so an array in the encoding the compositor carries, where byte 128 is
  ``a = 0``, came back 128 off on both axes. Not a rounding gap but a different
  colour: a flat ``Lab(60, 25, 25)`` converted to RGB as ``(0, 187, 255)``
  where Photoshop puts it at ``(196, 126, 101)``. Every Lab document was
  affected, and ``composite()`` disagreed with
  :py:meth:`~psd_tools.api.psd_image.PSDImage.topil` on the same file --
  ``topil()`` builds with ``Image.merge()``, which writes the planes verbatim
  and was right all along. The planes are now merged the same way, and three of
  the five Lab documents in the test corpus composite bitwise-identically to
  Photoshop's own preview where before every one of them was 128 out.

  ``numpy()`` and :py:func:`psd_tools.composite.composite` were never affected;
  the arrays were correct and only the PIL step corrupted them. Note that
  ``np.asarray()`` on a ``"LAB"`` image reads PIL's internal buffer rather than
  the values ``getpixel()`` reports, which is why the round trip looked right
  (#759).

- [fix] Size and interpret a colour-noise gradient from the document rather
  than from its descriptor. A noise gradient carries a colour space of its own
  -- Photoshop offers RGB, HSB and Lab, and keeps whichever was chosen in every
  document mode -- but the synthesized table was built three wide and passed
  through as if it were always RGB. Two consequences, both fixed here:

  A noise gradient on a document that is not three channels raised
  ``AssertionError: source has 3 channels, expected 1 or N`` out of the
  compositor's width check -- every CMYK, grayscale, bitmap, duotone and
  (unless its spot count happened to be three) multichannel document.

  An HSB or Lab noise gradient rendered the wrong colours everywhere, including
  on the RGB documents that did not raise: its components were read as RGB, so
  a hue of 30 degrees at ``[8.33, 60, 80]`` rendered ``(21, 153, 204)`` where
  Photoshop renders ``(204, 143, 82)``. The three spaces are now converted to
  the document's own, with Lab landing in a Lab document unconverted because
  the stored percentage already *is* that array's encoding. No gradient that
  rendered correctly before changed value (#730, #758).

- [fix] Read an HSB fill colour's hue as the angle it is. The descriptor's hue
  key is degrees, so a full turn is 360, but it was being divided by 300: every
  non-zero hue came out rotated -- ``HSB(120, 50, 80)`` rendered
  ``(102, 204, 143)`` where Photoshop renders ``(102, 204, 102)`` -- and hue
  360 landed past the end of the six-sector table, so a fully saturated red
  rendered white (#754).

  :py:func:`psd_tools.color_convert.hsb_to_rgb` now treats hue as cyclic
  throughout, so any value outside ``[0, 1)`` wraps into it instead of falling
  back to grey, and a non-finite hue degrades to the achromatic answer rather
  than raising. Previously only an exact ``1.0`` was handled.

- [fix] Convert a Lab fill colour across colour modes instead of passing the
  numbers through. Two mirror-image gaps, both closed here because they share
  the conversion: a Lab descriptor on a **non**-Lab document was read with a
  ``/255`` divisor that suited none of its three components, and any other
  descriptor class on a **Lab** document was written into the Lab arrays
  uninterpreted. Red on a Lab document arrived as ``(1.0, 0.0, 0.0)`` -- white
  at the extreme green-blue corner -- where the answer is
  ``(0.543, 0.819, 0.776)``.

  ``psd_tools.color_convert`` gains :py:func:`~psd_tools.color_convert.lab_to_rgb`
  and :py:func:`~psd_tools.color_convert.rgb_to_lab`, D50 with Bradford-adapted
  sRGB matrices, matching Photoshop's own colour engine to 0.05 Lab units
  converting in and a mean of 0.35/255 converting out. Lab values there are in
  native CIE units -- ``L`` 0..100 and signed ``a``/``b`` -- which is the one
  exception to the module's normalized-float rule, and the module now has a
  reference page.

  Backwards-incompatible in what it renders, for two cases that no Photoshop
  file can contain -- Photoshop rewrites a fill descriptor into the document's
  own colour class on save, so both need a third-party writer. Beyond the
  conversion itself, the **reduction curve moves** for a Lab fill on a
  grayscale, bitmap, duotone or multichannel document: it was ``L/255`` and is
  now the BT.601 luminance of the converted colour, so even a neutral changes
  (``Lab(50, 0, 0)`` goes from 0.196 to 0.466). A grey fill on a Lab document
  changes too, from the raw grey to its ``L*``; the single-channel *widening*
  path deliberately still does not convert, and says why (#743, #752).

- [fix] Read a Lab fill colour with the right divisor for each of its three
  components. ``L``, ``a`` and ``b`` were all divided by 255, which suits none
  of them: ``L`` runs 0..100, and ``a``/``b`` are signed and stored offset by
  128, so a neutral ``a = 0`` landed at the extreme end of its axis instead of
  in the middle. A near-neutral mid-tone therefore rendered as a dark,
  heavily saturated colour. Measured against a Photoshop-authored Lab document
  the old reading was out by up to 155/255; the corrected one reproduces
  Photoshop's own render of fourteen swatches spanning both ends of each chroma
  axis to within 1/255. Affects solid-colour, gradient and stroke fills
  authored with a Lab colour on a Lab document -- Pantone and other book
  colours, which is how they arise in practice. Out-of-range components now
  clamp to the end of their axis rather than wrapping to an unrelated colour.
  The same offset encoding corrects two neutral a/b constants that were spelled
  0.5, half a code value below the byte Photoshop writes: the artboard
  background default and the single-channel widening added in #722.

  Lab descriptors on a *non*-Lab document were left to the entry above, which
  replaces the ``/255`` reading for them with a real conversion (#743).

- [fix] Convert rather than replicate when a single-channel canvas is widened
  to a CMYK or Lab document's channel count. A grey ``g`` became ``(g, g, g, g)``
  in CMYK -- a heavily over-inked colour that is not the grey it came from --
  and ``(L, L, L)`` in Lab, where a lightness copied onto the a/b axes is the
  opposite of neutral. CMYK now transforms through the document's embedded ICC
  profile, matching Photoshop's own conversion to within 3/255 across a grey
  ramp where replication was out by ~100/255, and a grey widened this way
  survives the round trip back out through ``apply_icc`` to within 3/255 --
  except very near black, which is outside the CMYK gamut and comes back up to
  7/255 lighter. A CMYK document with
  no usable profile falls back to the K-only formula a grey *fill* already uses.
  Lab becomes ``(g, 128/255, 128/255)``, a and b being offset-encoded so that
  128/255 is neutral. RGB is unchanged, and multichannel keeps replicating -- its spot
  planes have no colorimetric reading to convert into. Reachable when a caller
  hands a single-channel backdrop to a multi-channel document, or through a
  grayscale pattern fill (#722).

- [fix] Stop cross-mode fills writing ink-space CMYK into an inverted canvas.
  The compositor's CMYK arrays store what is *left* -- 1.0 is no ink, which
  ``topil()`` inverts back on the way out -- but the three conversions into CMYK
  in ``composite/paint.py`` handed them ``color_convert``'s ink-space output
  unchanged, where white is ``(0, 0, 0, 0)``. A white solid-colour, gradient or
  stroke fill on a CMYK document therefore composited to solid black, and a
  black one to a muddy CMY; the artboard background constants were inverted the
  same way. Fills authored from an RGB, grayscale, HSB or Lab descriptor are
  affected; a CMYK descriptor on a CMYK document always read correctly.
  ``psd_tools.color_convert`` is unchanged -- it is public API with a documented
  ink-space contract -- and the ``background_color`` docstring, which repeated
  the wrong spelling, is corrected (#747).

- [fix] Degrade the non-separable blend modes on documents whose colour array
  is neither three nor four channels wide instead of crashing. ``Hue``, ``Saturation``, ``Color``
  and ``Luminosity`` raised ``IndexError`` or ``ValueError`` on every
  single-channel document -- grayscale and duotone -- because they index
  channels 1 and 2 of an array that has only channel 0, while ``Darker Color``
  and ``Lighter Color`` did not raise but returned the backdrop unchanged
  whatever the source was. A document wider than CMYK was broken too, there
  raising for all six. Photoshop offers none of these six modes on such a
  document, so there is no result to reproduce and they now fall back to
  ``Normal`` with a debug log, as ``Dissolve`` already does. RGB and CMYK are
  unaffected, and Lab is three channels wide so it keeps its existing
  as-if-RGB treatment -- Photoshop does offer all six modes there (#735).

- [fix] Let a per-channel colour be set on a multichannel document.
  :py:attr:`~psd_tools.api.psd_image.PSDImage.background_color` validated the
  sequence against a table whose multichannel entry is 64 -- the format's
  maximum number of channels, not any file's own count -- so every sequence was
  rejected and only a scalar could be set. Since ``background_color`` is the
  backdrop ``save()`` composites the merged preview against, a multichannel
  document had no way to be given a per-channel one.
  ``PSDImage.new("MULTICHANNEL", ...)`` was unsatisfiable for the same reason:
  it builds a one-channel document while the validator demanded 64
  (#731, #742).

- [fix] Size a fill from the document rather than from its descriptor. A solid
  colour, gradient or stroke takes its colour from a descriptor whose colour
  class is independent of the document's colour mode, and the width that came
  back was the descriptor's. Where that was neither one channel nor the
  document's own count the compositor's width assertion fired, which is what an
  RGB, CMYK or Lab descriptor did on a bitmap, duotone or multichannel
  document, a CMYK one on an indexed or Lab document, and a Lab one on a
  grayscale or CMYK document. An HSB descriptor was worse -- it raised
  ``ValueError`` on every mode but RGB and CMYK. Every descriptor class now
  converts to the document's width. No colour that already rendered changed
  value (#730, #742).

- [fix] Stop ``composite_pil()`` declaring a PIL mode that its pixel array does
  not match. The mode and the array were chosen separately, and they could
  disagree in three ways -- two of which produced pixels that corresponded to
  nothing in the file, and one of which raised (#729):

  A multichannel document came back **garbled**. Its colour array has one plane
  per spot channel, and the narrowing to the single plane PIL can hold was keyed
  on the mode and ran *after* alpha had been appended -- by which point the mode
  was ``"LA"`` and no longer matched, so it never fired. ``Image.fromarray()``
  does not reject a four-plane array declared as two: it reads two bytes out of
  every four, and the planes that came back corresponded to nothing in the file.
  The narrowing now happens before alpha is appended, and the dropped channels
  are announced with a warning instead of being lost silently. Use
  :py:func:`psd_tools.composite.composite` to keep every channel.

  Under ``force``, bitmap, CMYK and Lab documents **raised**. ``"A"`` was
  appended to the mode whether or not an alpha variant of it exists, so those
  asked ``Image.fromarray()`` for ``"1A"``, ``"CMYKA"`` and ``"LABA"`` and got
  ``ValueError: unrecognized image mode`` or ``TypeError: Cannot handle this
  data type``. Of the modes this function can produce, only ``"L"`` and
  ``"RGB"`` have an alpha variant, so for the others the alpha is no longer
  packed into the array -- it is handed to ``post_process()``, which still
  carries it for CMYK by converting to RGB first. So ``force=True`` on a CMYK
  document now returns the same ``"RGBA"`` that ``force=False`` always did.
  Bitmap results carry no alpha in either mode: ``post_process()`` applies it
  only to ``"RGB"`` and ``"L"``, and the ICC conversion that gets CMYK there
  cannot reach a 1-bit image -- little-cms builds no transform for one, so the
  profile is skipped and the mode stays ``"1"``. Lab results carry none either,
  for a third reason: a Lab document with an ICC profile raises before it gets
  that far -- #740.

  A bitmap document came back **garbled in both modes**.
  ``Image.fromarray(uint8, "1")`` does not mean "these bytes, as bilevel": PIL
  reads the raw mode literally at one bit per pixel, consuming one byte per
  eight columns and expanding its bits across the row, so a 4x4 document
  returned the bits of its first four bytes. The plane is now built as ``"L"``,
  where a byte is a pixel, and reduced afterwards. That was also the
  compositor's only ``Image.fromarray()`` call whose ``mode`` reinterprets the
  array's data type -- the use Pillow deprecated and removes in Pillow 13 --
  so it no longer warns. Passing ``mode`` where it matches the dtype, as the
  other colour modes do, is unaffected.

  Of the 284 fixtures outside ``third-party-psds``, rendered in both modes:
  every ``force=False`` render is bitwise identical except the bitmap one, and
  under ``force`` seventeen renders that previously raised now return an image,
  while exactly one changes from one image to another -- the garbled
  multichannel document.
- [fix] Correct pass-through group compositing when the group opacity is below
  255. The group's contribution was blended against the backdrop twice, so a
  partially transparent backdrop bled its colour into the result and the output
  varied with nesting depth (#703, #706).
- [fix] Detect the real user mask header from the channel list rather than by
  record length alone. ``MaskData`` misidentified its presence, so
  ``user_mask_density``, ``user_mask_feather``, ``vector_mask_density`` and
  ``vector_mask_feather`` returned ``None`` for affected files (#693, #704).
- [fix] Accept every scalar spelling of the composite backdrop. ``color=1`` and
  ``color=np.float32(1.0)`` raised ``TypeError`` because only ``float`` was
  recognised as a scalar. The backdrop is now normalised once at the API
  boundary rather than reinterpreted at each point of use (#708, #709).
- [fix] Recognise a transparent backdrop given as a NumPy scalar, a 0-d array,
  or a per-pixel array of zeros. Compositing a document with no layers used
  ``alpha=np.float32(0.0)`` as if it were opaque, which whitened every
  uncovered pixel (#708).
- [fix] Reject a multi-channel backdrop ``alpha``. Alpha is single-channel by
  definition, but a wider array was accepted and reached ``composite_pil()``,
  which concatenates it onto the colour array and built an image of the wrong
  width (#708).
- [fix] Composite over a single-channel backdrop array in a multi-channel
  document. The compositor's colour canvas was widened lazily at the first
  source layer, so a document with no source to apply -- every layer filtered
  out or invisible, or a document whose only layers are adjustments -- kept a
  one-channel array and raised ``TypeError`` from ``Image.fromarray()`` or
  ``ValueError: Channel count does not match colormode``. The channel count is
  now fixed when the compositor is built (#710).
- [fix] Reject a backdrop whose channel count is neither 1 nor the document's.
  A three-channel backdrop against a CMYK document used to surface as a NumPy
  broadcast error from inside the blend arithmetic (#710).
- [fix] Composite a layerless multichannel document over a backdrop. The
  backdrop was sized from ``EXPECTED_CHANNELS``, which reports 64 channels for
  multichannel documents regardless of how many the file actually carries, so
  the blend raised ``ValueError`` (#708).
- [fix] Composite a multichannel document that *has* layers. The same
  ``EXPECTED_CHANNELS`` count of 64 sized the backdrop on the layered path, so
  the canvas was built 64 channels wide and the first layer met it with an
  ``AssertionError``. The width now comes from the document header. Note that
  this fixes the NumPy ``composite()`` entry point; ``PSDImage.composite()``
  keeps only the first spot channel for multichannel documents, as it already
  did for layerless ones (#720).
- [fix] Never let the ``max_alloc_bytes`` estimate in ``composite()`` fall
  below the canvas it guards. The guard is there to reject a hostile file
  *before* it allocates, but it was given the header's channel count alone,
  which under-counted an indexed document's canvas by 3x -- its single stored
  channel becomes three through the palette. It is now given the wider of the
  header count and the canvas width, so no colour mode under-estimates. This
  can reject a document that a very tight budget previously admitted. Applies
  to ``composite()``'s own guard only: a document with no layers returns early,
  before that estimate, and falls to the check in ``numpy()``, which was fixed
  separately (#720, #732).
- [fix] Never let the ``max_alloc_bytes`` estimate in ``numpy()`` fall below
  the array it guards. ``get_image_data()`` was given the header's channel
  count, which is below what it goes on to allocate for an indexed document:
  the palette is applied to the whole buffer, so each stored channel becomes
  three and the estimate was threefold short. Flattened indexed documents are
  what Photoshop ordinarily writes, and such a document takes the zero-layer
  early return in :py:func:`psd_tools.composite.composite`, which leaves this
  the only estimate on that path. The count is now multiplied by the palette
  expansion, so it matches the allocation exactly for every colour mode, depth
  and channel count. This can reject a document that a very tight budget
  previously admitted, and only an 8-bit indexed one (#732).

  Note that the header's channel count is not cross-checked against the colour
  mode, so the expansion scales with it: a header declaring eight channels
  allocates twenty-four planes. The guard is sized for that, since it exists to
  bound hostile headers rather than well-formed ones.

  The same entry point no longer over-estimates its synthesised results either.
  ``numpy("mask")``, and ``numpy("shape")`` on a document with no transparency,
  return a ``(h, w, 1)`` array without reading the image data, but were
  estimated at the document's stored width -- so a budget that fitted such a
  request four times over could still reject it on a CMYK document. That
  over-estimate was not specific to indexed and predates this entry.

  The estimate bounds the array that is returned, which is what
  ``check_pixel_size()`` has always measured. Peak usage during parsing is a
  small multiple of it for every colour mode; that predates this entry and is
  unchanged by it. 1-bit documents were under-counted eightfold for want of a
  depth term, which predated this entry as well and is fixed by the #737 entry
  above, in this same release.
- [fix] Composite duotone documents at their stored width.
  ``EXPECTED_CHANNELS`` reported 2 for duotone -- the ink count -- while duotone
  pixel data is a single grayscale channel, the one to four ink curves living
  in the colour mode data section. Three consequences, all fixed:
  ``composite()`` returned a two-channel array whose second channel was not
  data from the file but the backdrop copied; ``PSDImage.composite(force=True)``
  returned *wrong pixels*, because the over-wide array was handed to PIL as
  ``"LA"`` and the planes came out shifted against each other; and seven blend
  modes -- ``ColorBurn``, ``ColorDodge``, ``HardLight``, ``LinearLight``,
  ``PinLight``, ``SoftLight`` and ``VividLight`` -- raised ``IndexError`` on any
  duotone document. Photoshop keeps layers in duotone mode, so every one of
  these was reachable on ordinary files (#733).

  ``Hue``, ``Saturation``, ``Color`` and ``Luminosity`` still raise on a duotone
  document. They raise identically on a grayscale one, so that is a pre-existing
  limitation of single-channel documents rather than anything this entry
  changes; it is tracked in #735.
- [fix] Read the alpha channel of a duotone document as alpha. Because the
  colour array was taken to be two channels wide, a duotone file carrying a
  transparency channel returned it as *colour* data from ``numpy("color")``,
  and ``has_transparency()`` reported ``False`` -- while ``pil_mode`` said
  ``"LA"``, so the document contradicted itself. No fixture has this shape
  (#733).
- [api] ``PSDImage.new("DUOTONE", ...)`` now accepts a colour. It previously
  rejected every sequence: the constructor demanded two components while the
  header it built declared one channel, so no value satisfied both (#733).

  **Backwards incompatible**: a per-channel ``background_color`` on a duotone
  document now takes one component instead of two.
  ``psd.background_color = (0.5, 0.5)`` raises ``ValueError``; pass ``(0.5,)``
  or a scalar. The second component was inert -- it had no channel to be
  written to, and the saved bytes are identical without it (#733).
- [api] Widen the ``color`` parameter of ``composite()``, ``composite_pil()``,
  ``Layer.composite()``, ``Group.composite()``, ``Artboard.composite()`` and
  ``PSDImage.composite()`` -- and of ``LayerProtocol`` and ``PSDProtocol`` --
  from ``float | tuple[float, ...] | np.ndarray`` to
  ``float | Sequence[float] | np.ndarray``, matching what is accepted at
  runtime. This is a widening; existing calls are unaffected (#708).

  **Backwards incompatible**: a per-channel backdrop whose length disagrees
  with the document's colour mode now raises ``ValueError`` instead of being
  silently accepted. ``psd.composite(color=(1.0, 1.0, 1.0))`` against a
  grayscale or bitmap document previously produced a three-channel result that
  was then reduced to its first channel; pass a scalar, or a sequence matching
  ``psd.color_mode``.
- [fix] Apply a pattern overlay effect to a single-channel layer in a
  multi-channel document. The effect took its target channel count from the
  layer's own colour rather than from the document, so an RGB pattern over a
  grayscale layer was rejected with ``AssertionError: Inconsistent pattern
  channels.`` even though the pattern matched the document (#711).
- [fix] Apply a stroke layer effect to a layer that has no mask. The mask
  coverage is a bare scalar in that case, which the stroke effect handed
  straight to an array routine, raising ``AttributeError: 'float' object has no
  attribute 'shape'``. Reachable for a fill layer with no vector mask (#711).
- [fix] Implement Knockout compositing (#707). Groups and layers with Knockout
  enabled previously rendered as if the setting were absent. Shallow knockout
  now punches through to the enclosing group's backdrop, and deep knockout to
  the document backdrop -- passing through enclosing pass-through groups but
  stopping at an isolated one, and at the Background layer where the document
  has one. Also distinguishes shallow from deep, which were read as a single
  boolean, via the new ``psd_tools.constants.Knockout`` enum.

  **Backwards incompatible**: documents that combine Knockout with a fill
  opacity below 100% now render differently. Documents without Knockout, or
  with Knockout at fill opacity 100% -- where it has no visible effect by
  design -- are unaffected.

1.18.0 (2026-08-07)
-------------------

- [security] Confine external smart object reads to a directory by default; add ``trust_full_path`` opt-in to restore the previous behaviour (GHSA-r6c8-3pw3-m54g)
- [chore] Bump dependencies: ruff to 0.16.0, mypy to 2.3.0, pillow to 12.3.0, typing-extensions to 4.16.0, pre-commit to 4.6.1, cibuildwheel to 4.1.1, actions/stale to 11

1.17.4 (2026-06-24)
-------------------


- [security] Guard against oversized memory allocation from failed channel
  decompression (CWE-789, related to GHSA-8q6g-vjhf-jp8m)
- [api] Add ``max_alloc_bytes`` parameter to ``PSDImage.open()`` for an
  opt-in per-document allocation budget cap

1.17.3 (2026-06-22)
-------------------

- [security] Guard against uncontrolled memory allocation via crafted PSD canvas dimensions (GHSA-8q6g-vjhf-jp8m, #676)
- [fix] Fix VirtualMemoryArray dimension computation for patterns (#672)
- [fix] Fix smart object blank filetype field handling (#663)
- [chore] Bump ruff to 0.15.18, pytest to 9.1.1, actions/checkout to v7

1.17.2 (2026-06-04)
-------------------

- [fix] Disable Limited API for Windows Cython extension (#661)
- [chore] Bump ruff from 0.15.14 to 0.15.15 (#659)

1.17.1 (2026-05-27)
-------------------

- [security] Fix path traversal in ``SmartObject.save()`` and ``open()`` (GHSA-2rmg-vrx8-9j2f, #657)
- [chore] Bump ruff to 0.15.14, mypy to 2.1.0

1.17.0 (2026-05-11)
-------------------

- [composite] Add Hue/Saturation adjustment layer composite algorithm (#646)
- [fix] Fix float32 safety in Hue/Saturation composite algorithm (#646)
- [refactor] Use ``IO[bytes]`` instead of ``BinaryIO`` throughout the codebase (#647)
- [fix] Fix mypy 2.0 strict-bytes errors in ``rle.py``
- [ci] Migrate pre-commit hooks to uv-local runners; expand ruff and mypy scope (#650)
- [chore] Bump mypy to 2.0.0, ruff to 0.15.12, pre-commit to 4.6.0

1.16.0 (2026-04-24)
-------------------

- [composite] Add adjustment layer compositing support and fix pass-through compositing logic (#628)
- [fix] Fix fallback logic and density computation for user masks
- [refactor] Refactor composite subpackage for type safety and stability (#640)
- [docs] Update README and usage docs to reflect adjustment layer compositing support
- [chore] Bump ruff to 0.15.11, mypy to 1.20.1

1.15.0.post1 (2026-04-14)
--------------------------

- [ci] Fix release packaging: version.py was not bumped in the v1.15.0 release PR, causing wheels to be built with the wrong version

1.15.0 (2026-04-14)
-------------------

- [api] Add ``layer_sized`` option to ``Mask.topil()`` for correct rendering of inverted masks (#622, fixes #389)
- [fix] Graceful fallback for zero-length channel data (#621, fixes #398)
- [fix] Make artboard background color color-mode aware (#620, fixes #395)
- [fix] Normalize color space in composite paint to fix mixed-colorspace stroke error (#618, fixes #397)
- [fix] Compute ``VectorMask.bbox`` from full Bézier curve extent, not just anchors (#613)
- [refactor] Extract color conversion math into ``psd_tools.color_convert`` module (#630)
- [docs] Fix misleading ``ImageResource`` signature docstring (#624, fixes #375)
- [ci] Add Python 3.14 free-threaded (cp314t) wheel support (#633)
- [ci] Automate release tagging via ``pull_request`` closed event (#611)
- [ci] Add stale issue/PR workflow (#615)
- [chore] Bump pytest to 9.0.3, ruff to 0.15.10, actions/checkout to v6 (#625, #626, #627)

1.14.3 (2026-04-10)
-------------------

- [security] Upgrade Pygments to 2.20.0 to resolve ReDoS vulnerability (#609)
- [fix] Don't add ``USER_LAYER_MASK`` when PSD mode already carries transparency (#608)
- [chore] Bump Pillow from 12.1.1 to 12.2.0, mypy to 1.20.0, ruff to 0.15.9

1.14.2 (2026-03-19)
-------------------

- [fix] Detect transparency from negative ``layer_count`` in preview path (#595)

1.14.1 (2026-03-17)
-------------------

- [fix] Preserve alpha channel when compositing from layers (#593, fixes #592)
- [chore] Bump ruff from 0.15.4 to 0.15.6, pypa/cibuildwheel from 3.3.1 to 3.4.0

1.14.0 (2026-03-03)
-------------------

- [api] Add ``PSDImage.background_color`` property for reading and writing document background color (#586)
- [api] Add high-level typesetting API for ``TypeLayer`` text manipulation (#579)
- [fix] Update contributing link from master to main branch (#580)
- [chore] Bump sphinx-rtd-theme from 3.0.2 to 3.1.0, ruff from 0.15.2 to 0.15.4
- [ci] Bump actions/upload-artifact from 6 to 7, actions/download-artifact from 7 to 8

1.13.1 (2026-02-27)
-------------------

- [psd] Fix ``TransferFunction`` curve values parsed as unsigned instead of signed shorts (#577)
- [psd] Handle truncated ``MaskParameters`` data gracefully (#574, fixes #573)
- [refactor] Drop Python <3.11 typing compatibility guards (#575)
- [docs] Improve mask module documentation and index layout (#576)

1.13.0 (2026-02-26)
-------------------

- [api] Add ``Layer.sheet_color`` property for reading and writing Photoshop layer color labels (#546)
- [api] Add ``Layer.create_mask()``, ``remove_mask()``, and ``update_mask()`` for pixel mask CRUD operations (#568)
- [api] Auto-create layer masks from alpha channel in ``PixelLayer.frompil()`` (#568)
- [api] Add ``Mask.disabled`` setter for toggling layer mask visibility (#568)

1.12.2 (2026-02-24)
-------------------

- [api] Fix bbox to exclude clipping layers by default; add ``include_clipping`` parameter to ``Group.extract_bbox()`` (#566, fixes #547)
- [api] Fix UTF-16 surrogate pair handling for emoji in text layers (#551)
- [security] Fix compression security issues (GHSA-24p2-j2jr-386w) (#549)
- [ci] Fix least-privilege permissions in CI workflows (#550)
- [ci] Add pre-commit hooks for linting, formatting, and type checking (#552)
- [ci] Add Dependabot configuration for automated dependency updates (#555)
- [dev] Extend mypy and ruff coverage to the tests directory (#554)
- [docs] Clean up developer setup documentation (#553)
- [chore] Bump Pillow from 11.3.0 to 12.1.1 (#563)
- [chore] Bump attrs, ipykernel, mypy, pytest, and various GitHub Actions

1.12.1 (2025-12-05)
-------------------

- [api] Fix preview image mode when saving PSD files (#542)
- [packaging] Upgrade aggdraw to >=1.4.1 for Python 3.14 Windows support (#543)

1.12.0 (2025-11-17)
-------------------

- [packaging] Make composite dependencies optional via ``psd-tools[composite]`` extra (#525)
- [api] Lazy-load advanced composite features (vector masks, gradients, effects) to avoid importing optional dependencies unless needed
- [api] Basic numpy-based compositing works without ``scipy``, ``scikit-image``, or ``aggdraw``
- [api] Composite functionality raises ``ImportError`` with installation instructions only when advanced features are used
- [api] Handle missing composite dependencies gracefully in ``PSDImage.save()`` (#532)
- [packaging] Move ``aggdraw``, ``scipy``, and ``scikit-image`` to optional dependencies
- [packaging] Keep ``numpy`` as core dependency for raw pixel data access
- [refactor] Move ``PSD`` class to dedicated ``document`` module (#530)
- [refactor] Reorganize composite module structure and add type safety (#524)
- [refactor] Split utils module into registry and bin_utils (#537)
- [refactor] Create shared API utils module (#538)
- [refactor] Improve type annotations and standardize imports (#539)
- [api] Add comprehensive type annotations to psd_tools package (#536)
- [tests] Add comprehensive type annotations to test suite (#534, #535)
- [tests] Add CI testing without composite dependencies (#533)
- [docs] Enhance package and module docstrings with comprehensive documentation (#531)
- [docs] Update installation instructions for optional composite support (#527)
- [docs] Convert README to Markdown (#527)
- [ci] Fix CI status badge in README (#523)
- [ci] Fix ReadTheDocs build by adding Self import fallback
- [ci] Fix Python 3.10 mypy compatibility (#526)
- [chore] Remove unused deprecated decorator (#529)
- [chore] Remove redundant MANIFEST.in file (#528)

**Breaking change**: Users who rely on advanced composite features (vector masks, gradient fills,
pattern fills, stroke effects) must now install with ``pip install 'psd-tools[composite]'`` or
install the optional dependencies separately. Basic pixel layer compositing continues to work
with just numpy. This change enables support for Python 3.14 on Windows and other platforms
where composite dependencies may not be available.

1.11.1 (2025-11-17)
-------------------

- [ci] Disable Python 3.14 on Windows due to aggdraw unavailability (#521)

1.11.0 (2025-11-09)
-------------------

- [api] Add public APIs for layer and group creation (#517)
- [api] Type safety improvements (#516)
- [api] Refactor ``psd_tools.api`` import dependencies (#515)
- [api] Fix group blend mode returning None (#514)
- [dev] Add Claude Code support (#511)
- [api] Add type annotation to more APIs (#509, #510, #512)
- [api] Add ``fill_opacity`` and ``reference_point`` attributes (#507, #508)
- [psd] Improve pretty print of Subpath (#506)

1.10.13 (2025-10-02)
--------------------

- [docs] Fix incorrect method name in the usage (#504)
- [api] Fix updated status flag (#503)
- [api] Add tree traversal API (#502)
- [psd] Fix crash when reading malformed Levels record (#501)

1.10.12 (2025-09-25)
--------------------

- [api] Drop docopt dependency (#498)
- [api] Remove unused imports (#497)
- [api] Fix stacked clip layer handling (#496)

1.10.11 (2025-09-24)
--------------------

- [tests] Drop python2 compatibility code (#494)
- [api] Fix clip layer handling (#493)
- [psd] Workaround CAI tagged block reconstruction (#492)

1.10.10 (2025-09-18)
--------------------

- [api] Fix clipping with stroke composite (#489)
- [ci] Fix documentation build (#486, #487)
- [ci] Introduce ABI3 wheels (#483, #485)
- [api] Fix PyCMSError in composite (#484)
- [api] Fix ImageMath deprecation warning (#482)

1.10.9 (2025-08-07)
-------------------

- [psd] Allow linked layer version 8 (#476)

1.10.8 (2025-06-06)
-------------------

- [ci] Update CI configuration (#471)
- [psd] Workaround levels adjustment layer parsing (#470)
- [psd] Support CAI, GenI, OCIO tagged blocks (#469)

1.10.7 (2025-02-25)
-------------------

- [psd] Fix missing gradient method (#465)

1.10.6 (2025-02-18)
-------------------

- [security] Update pillow dependency (#462)

1.10.5 (2025-02-18)
-------------------

- [security] Update pillow dependency (#461)

1.10.4 (2024-11-25)
-------------------

- [api] Allow Path objects for PSDImage open (#452)

1.10.3 (2024-11-20)
-------------------

- [psd] Fix data corruption by irregular OSType (#449)
- [api] Add type annotation to the high-level APIs (#448)


1.10.2 (2024-10-23)
-------------------

- [api] Add channel info via DisplayInfo (#443)
- [api] Support layer locking (#442)


1.10.1 (2024-10-10)
-------------------

- [api] Fix artboard creation (#438)
- [api] Fix layer conversion issue (#435)

1.10.0 (2024-09-26)
-------------------

- [api] Support basic layer structure editing (#428)
- [api] Drop deprecated compose module (#432)

1.9.34 (2024-07-01)
-------------------

- [api] Support text type property (#419)
- [psd] Improve RLE decoding error handling (#417)

1.9.33 (2024-06-14)
-------------------

- [psd] Raise IO error instead of assertion (#413)
- [api] Add a new property to SmartObject: transform_box (#412)
- [ci] Migrate code formatter to ruff (#408)

1.9.32 (2024-05-01)
-------------------

- [psd] Fix incorrect group divider handling (#399)

1.9.31 (2024-02-26)
-------------------

- [psd] Reworked packbits/rle algorithms (#392)

1.9.30 (2024-01-06)
-------------------

- [ci] Fix missing pyx file in sdist (#386)

1.9.29 (2024-01-04)
-------------------

- [ci] Update CI configuration (#383)
- [dev] Migrate the builder to pyproject.toml
- [dev] Update linter and formatter to pysen
- [dev] Deprecate tox
- [psd] Add new color sheet (#380)
- [psd] Fix transparency check (#370)

1.9.28 (2023-07-04)
-------------------

- [psd] Add alternate 8ELE signiture for 8BIM tagged block (#367)

1.9.27 (2023-06-27)
-------------------

- [composite] Fix regression by #361 (#364)

1.9.26 (2023-06-21)
-------------------

- [composite] Read HSB colors in RGB and CMYK color modes (#361)
- [ci] Update CI configuration (#362)

1.9.25 (2023-06-19)
-------------------

- [composite] Fix hue, sat, and vivid light (#359)

1.9.24 (2023-01-17)
-------------------

- [psd] Support float RGB values (#350)
- [psd] Workaround stroke class ID (#346)
- [ci] Update CI configuration (#347)
- [composite] Fix group clipping (#336)

1.9.23 (2022-09-26)
-------------------

- [api] Add bbox invalidation when toggling layer visibility (#334)

1.9.22 (2022-09-09)
-------------------

- [psd] Add support for v3 gradient map adjustment layer (#330)


1.9.21 (2022-06-18)
-------------------

- [api] Fix incorrect has_effects behavior (#322)
- [composite] Improve blending numerical stability (#321)
- [composite] Improve non-RGB modes and transparency (#319, @Etienne-Gautier)
- [psd] Workaround assertion error in broken file (#320)

1.9.20 (2022-05-16)
-------------------

- [ci] Update CI configuration (#313 #314)
- [composite] Fix composite errors (#312)
- [psd] Suppress vowv tagged blocks (#306)

1.9.19 (2022-04-15)
-------------------

- [composite] Fix rasterized shape composite (#301 #302)

1.9.18 (2021-08-20)
-------------------

- [api] Fix missing effect attributes (#284)
- [package] Support additional platforms (i686, aarch64, universal2, win32)
- [package] Drop py36 support

1.9.17 (2021-01-15)
-------------------

- [api] Fix incorrect fill layer parse (fix #254)

1.9.16 (2020-09-24)
-------------------

- [package] Drop py27 and py35 support
- [psd] Workaround Enum bug (fix #241)
- [composite] Fix transparency issue (fix #242)
- [composite] Fix mask disable flag (fix #243)
- [api] Add workaround for creating PSB (fix #246)
- [api] Fix incorrect adjustment parse (fix #247)

1.9.15 (2020-07-17)
-------------------

- [composite] Fix ignored clip layers for groups.
- [composite] Fix out-of-viewport stroke effect.

1.9.14 (2020-07-10)
-------------------

- [api] Bugfix for PSDImage composite layer_filter option.
- [api] Bugfix for transparency and alpha distinction.
- [psd] Rename COMPOSITOR_INFO.
- [composite] Fix stroke effect target shape.

1.9.13 (2020-05-25)
-------------------

- [api] Bugfix for PSDImage init internal.

1.9.12 (2020-05-20)
-------------------

- [psd] Bugfix for CurvesExtraMarker read.

1.9.11 (2020-05-01)
-------------------

- [composite] Fix layer check.

1.9.10 (2020-04-21)
-------------------

- [psd] Fix engine data parser.

1.9.9 (2020-03-30)
------------------

- [composite] Fix stroke effect argument.

1.9.8 (2020-03-18)
------------------

- [composite] Fix incorrect fill opacity handling in compositing.
- [composite] Fix incorrect alpha for patterns.

1.9.7 (2020-03-17)
------------------

- [composite] Fix path operation for merged components.
- [composite] Fix vector mask compositing condition.

1.9.6 (2020-03-16)
------------------

- [composite] Fix incorrect alpha channel handling in composite.

1.9.5 (2020-03-11)
------------------

- [api] Add ignore_preview option to `PSDImage.composite`.
- [composite] Improve stroke effect composition for vector masks.
- [composite] Avoid crash when there is an erroneous subpath.
- [composite] Workaround possible divide-by-zero warn in stroke composition.
- [composite] Fix incorrect pattern transparency handling.
- [composite] Fix ignored effects in direct group composition.
- [composite] Fix incorrect opacity handling for clip layers.

1.9.4 (2020-03-11)
------------------

- [compression] Security fix, affected versions are 1.8.37 - 1.9.3.

1.9.3 (2020-03-10)
------------------

- [composite] Fix memory corruption crash for pattern data in PSB files.
- [psd] Add image data pretty printing.

1.9.2 (2020-03-03)
------------------

- [psd] Add missing resource ID.
- [psd] Fix pretty printing regression.
- [psd] Fix big tag key for linked layers.
- [psd] Support frgb tag.
- [psd] Support sgrp metadata key.
- [psd] Support patt tag.
- [psd] Workaround unknown engine data.

1.9.1 (2020-02-28)
------------------

- [psd] Minor bugfix.

1.9.0 (2020-02-26)
------------------

- [composite] Implement NumPy-based compositing functionality.
- [composite] Support blending modes other than dissolve.
- [composite] Support blending in RGB, CMYK, Grayscale.
- [api] Introduce NumPy array export method.
- [api] Drop deprecated methods from v1.7.x such as `as_PIL`.
- [api] Deprecate `compose` method.
- [compression] Rename packbits to rle.
- [compression] Improve RLE decode efficiency.
- [tests] Additional compositing tests.

1.8.38 (2020-02-12)
-------------------

- [composer] fix crash when gradient fill is in stroke.

1.8.37 (2020-02-07)
-------------------

- [compression] Remove packbits dependency and introduce cython implementation.
- [deploy] Move CI provider from Travis-CI to Github Actions.
- [deploy] Start distributing binary wheels.

1.8.36 (2019-12-26)
-------------------

- [psd] add safeguard for malformed global layer mask info parser.

1.8.35 (2019-12-26)
-------------------

- [api] remove duplicate `has_mask()` definition.
- [composer] fix empty effects check.

1.8.34 (2019-11-28)
-------------------

- [api] fix `compose()` arguments.
- [psd] fix attrs version dependency.

1.8.33 (2019-11-28)
-------------------

- [api] add `include_invisible` option to `Group.extract_bbox`.
- [psd] fix deprecated attrs api.


1.8.32 (2019-11-28)
-------------------

- [psd] fix 16/32 bit file parsing bug introduced in 1.8.17.

1.8.31 (2019-11-27)
-------------------

- [psd] bugfix reading psb.
- [psd] bugfix reading slices resource.
- [security] update dependency to pillow >= 6.2.0.

1.8.30 (2019-09-24)
-------------------

- [psd] workaround for reading less-than-4-byte int in malformed psd files.

1.8.29 (2019-09-10)
-------------------

- [composer] fix vector mask bbox in composition.

1.8.28 (2019-09-09)
-------------------

- [api] fix `Effects.__repr__()` when data is empty.

1.8.27 (2019-08-29)
-------------------

- [api] accept encoding param in `PSDImage.open` and `PSDImage.save`.
- [deploy] bugfix travis deployment condition.


1.8.26 (2019-08-28)
-------------------

- [composer] support group mask.

1.8.25 (2019-08-07)
-------------------

- [api] change return type of `PSDImage.color_mode` to enum.
- [api] support reading of bitmap color mode.
- [api] support channel option in `topil()` method.

1.8.24 (2019-07-25)
-------------------

- [composer] experimental support of commutative blending modes.

1.8.23 (2019-06-24)
-------------------

- [composer] fix clipping on alpha-less image;
- [composer] fix stroke effect for flat plane;
- [composer] workaround for insufficient knots;
- [composer] fix for custom color space.

1.8.22 (2019-06-19)
-------------------

- fix pass-through composing bug;
- fix alpha blending in effect;
- fix vector mask composition;
- experimental support for shape stroke;
- experimental support for stroke effect.

1.8.21 (2019-06-18)
-------------------

- change effect property return type from str to enum;
- improve gradient quality;
- support fill opacity and layer opacity;
- add tmln key in metadata setting.

1.8.20 (2019-06-13)
-------------------

- support gradient styles.

1.8.19 (2019-06-11)
-------------------

- fix broken `psd_tools.composer.vector` module in 1.8.17;
- experimental support for color noise gradient;
- bugfix for clip masks;
- bugfix for CMYK composing.

1.8.17 (2019-06-05)
-------------------

- move `psd_tools.api.composer` module to `psd_tools.composer` package;
- support 19 blending modes in composer;
- support fill opacity;
- fix image size when composing with masks;
- rename `TaggedBlockID` to `Tag`;
- rename `ImageResourceID` to `Resource`;
- add `bytes` mixin to `Enum` constants;
- replace `Enum` keys with raw values in `psd_tools.psd.base.Dict` classes.

1.8.16 (2019-05-24)
-------------------

- fix broken group compose in 1.8.15;
- fix missing pattern / gradient composition in vector stroke content.

1.8.15 (2019-05-23)
-------------------

- coding style fix;
- fix `compose()` bbox option.

1.8.14 (2019-04-12)
-------------------

- add dependency to aggdraw;
- support bezier curves in vector masks;
- support path operations;
- fix `compose(force=True)` behavior;
- fix default background color in composer;
- improve pattern overlay parameters support;
- fix gradient map generation for a single stop.

1.8.13 (2019-04-05)
-------------------

- fix engine_data unknown tag format;
- fix compose for extra alpha channels;
- workaround for pillow 6.0.0 bug.

1.8.12 (2019-03-25)
-------------------

- add apply_icc option in pil io.

1.8.11 (2019-03-14)
-------------------

- introduce terminology module;
- reduce memory use in read;
- add main testing.

1.8.10 (2019-02-27)
-------------------

- fix PSB extn key size bug.

1.8.9 (2019-02-21)
------------------

- documentation updates;
- introduce `Artboard` class.

1.8.8 (2019-02-20)
------------------

- revert package name to `psd_tools`;
- prepare merging to the main repo.

1.8.7 (2019-02-15)
------------------

- minor bugfix.

1.8.6 (2019-02-14)
------------------

- change _psd pointer in PSDImage;
- add version property;
- support fill effects in composer.

1.8.5 (2019-02-05)
------------------

- change tagged block/image resource singleton accessor in user API;
- add documentation on iterator order;
- fix export setting 1 big key config;
- fix computer info big key config.

1.8.3 (2019-02-01)
------------------

- add channel size checking in topil;
- add mlst metadata decoding;
- fix key collision issue in descriptor;
- performance improvement for packbit encoding/decoding;
- drop cython dependency in travis config;
- implement thumbnail, is_group, and parent methods in PSDImage.

1.8.0 (2019-01-24)
------------------

- major API changes;
- package name changed to `psd_tools2`;
- completely rewritten decoding subpackage `psd_tools2.psd`;
- improved composer functionality;
- file write support;
- drop cython compression module and makes the package pure-python;
- drop pymaging support.

1.7.30 (2019-01-15)
-------------------

- composer alpha blending fix;
- documentation fix.

1.7.28 (2019-01-09)
-------------------

- support cinf tagged block.

1.7.27 (2018-12-06)
-------------------

- add missing extra image resource block signatures.

1.7.26 (2018-12-03)
-------------------

- move psd_tools tests under tests/psd_tools.

1.7.25 (2018-11-27)
-------------------

- fix alpha channel visibility of composed image.

1.7.24 (2018-11-21)
-------------------

- fix unit rectangle drawing size.


1.7.23 (2018-11-20)
-------------------

- fix ignored visibility in bbox calculation.

1.7.22 (2018-10-12)
-------------------

- drop py34 support;
- fix tobytes deprecation warning.

1.7.21 (2018-10-10)
-------------------

- fix gradient descriptor bug.

1.7.20 (2018-10-09)
-------------------

- fix coloroverlay bug;
- fix gradient angle bug;
- fix curves decoder bug.

1.7.19 (2018-10-02)
-------------------

- fix descriptor decoder.

1.7.18 (2018-09-26)
-------------------

- add shape rendering in `compose()`;
- add grayscale support.

1.7.17 (2018-09-21)
-------------------

- fix `has_pixel()` condition.

1.7.16 (2018-08-29)
-------------------

- fix fill opacity in `compose()`;
- workaround for broken `PrintFlags`.

1.7.15 (2018-08-28)
-------------------

- fix color overlay issue in `compose()`.

1.7.14 (2018-08-24)
-------------------

- fix `verbose` arg for python 3.7 compatibility.

1.7.13 (2018-08-10)
-------------------

- fix `has_pixel()` for partial channels;
- support color overlay in `compose()`.

1.7.12 (2018-06-25)
-------------------

- fix mask rendering in compose (Thanks @andrey-hider and @nkato).

1.7.11 (2018-06-11)
-------------------

- unicode bugfixes.

1.7.10 (2018-06-06)
-------------------

- fix descriptor decoding errors;
- minor bugfixes.

1.7.9 (2018-06-05)
------------------

- fix UnicodeError in exif;
- workaround for irregular descriptor name;
- add undocumented `extn` tagged block decoding;
- move duplicated icc module to subpackage;
- support PIL rendering with extra alpha channels.

1.7.8 (2018-05-29)
------------------

- update documentation;
- fix PEP8 compliance;
- rename merge_layers to compose.

1.7.7 (2018-05-02)
------------------

- fix white background issue in `as_PIL()`.

1.7.6 (2018-04-27)
------------------

- add quality testing;
- fix disabled mask.

1.7.5 (2018-04-25)
------------------

- fix `has_mask()` condition;
- add mask composition in `merge_layers()`;
- fix mask display.

1.7.4 (2018-03-06)
------------------

- fix infinity loop in `print_tree()`.

1.7.3 (2018-02-27)
------------------

- add vector origination API;
- fix shape and vector mask identification;
- change enum name conversion;
- update docs.

1.7.2 (2018-02-14)
------------------

- add adjustments API;
- add mask API;
- bugfix for tagged_blocks decoders.

1.7.1 (2018-02-08)
------------------

- add mask user API;
- add layer coordinate user API;
- add vector mask and vector stroke API;
- cleanup user API;
- add automatic descriptor conversion.


1.7.0 (2018-01-25)
------------------

- cleanup user API organization;
- remove json encoder api;
- make cli a package main.

1.6.7 (2018-01-17)
------------------

- workaround for anaconda 2.7 pillow;
- bbox existence checkf.

1.6.6 (2018-01-10)
------------------

- experimental clipping support in `merge_layer()`;
- revert `as_PIL()` in `AdjustmentLayer`.

1.6.5 (2017-12-22)
------------------

- Small fix for erroneous unicode path name

1.6.4 (2017-12-20)
------------------

- Add `all_layers()` method;
- Add `_image_resource_blocks` property;
- Add `thumbnail()` method.

1.6.3 (2017-09-27)
------------------

- documentation updates;
- github repository renamed to psd-tools2;
- AdjustmentLayer fix.

1.6.2 (2017-09-13)
------------------

- layer class structure reorganization;
- add Effects API;
- add TypeLayer API methods.

1.6 (2017-09-08)
----------------

- PSDImage user API update;
- user API adds distinct layer types;
- Sphinx documentation.

1.5 (2017-07-13)
----------------

- implemented many decodings of image resources and tagged blocks;
- implemented EngineData text information;
- user API for getting mask and patterns;
- user API to calculate bbox for shape layers;

1.4 (2017-01-02)
----------------

- Fixed reading of layer mask data (thanks Evgeny Kopylov);
- Python 2.6 support is dropped;
- Python 3.6 support is added (thanks Leendert Brouwer);
- extension is rebuilt with Cython 0.25.2.

1.3 (2016-01-25)
----------------

- fixed references decoding (thanks Josh Drake);
- fixed PIL support for CMYK files (thanks Michael Wu);
- optional C extension is rebuilt with Cython 0.23.4;
- Python 3.2 support is dropped; the package still works in Python 3.2,
  but the compatibility is no longer checked by tests, and so it can break
  in future.
- declare Python 3.5 as supported.

1.2 (2015-01-27)
----------------

- implemented extraction of embedded files (embedded smart objects) -
  thanks Volker Braun;
- optional C extension is rebuilt with Cython 0.21.2.
- hg mirror on bitbucket is dropped, sorry!

1.1 (2014-11-17)
----------------

- improved METADATA_SETTING decoding (thanks Evgeny Kopylov);
- layer comps decoding (thanks Evgeny Kopylov);
- improved smart objects decoding (thanks Joey Gentry);
- user API for getting layer transforms and placed layer size
  (thanks Joey Gentry);
- IPython import is deferred to speedup ``psd-tools.py`` command-line utility;
- ``_RootGroup.__repr__`` is fixed;
- warning message building is more robust;
- optional C extension is rebuilt with Cython 0.21.1.

1.0 (2014-07-24)
----------------

- Fixed reading of images with layer masks (thanks Evgeny Kopylov);
- improved mask data decoding (thanks Evgeny Kopylov);
- fixed synchronization in case of ``8B64`` signatures (thanks Evgeny Kopylov);
- fixed reading of layers with zero length (thanks Evgeny Kopylov);
- fixed Descriptor parsing (thanks Evgeny Kopylov);
- some of the descriptor structures and tagged block constants are renamed (thanks Evgeny Kopylov);
- PATH_SELECTION_STATE decoding (thanks Evgeny Kopylov);
- the library is switched to setuptools; docopt is now installed automatically.

0.10 (2014-06-15)
-----------------

- Layer effects parsing (thanks Evgeny Kopylov);
- trailing null bytes are stripped from descriptor strings
  (thanks Evgeny Kopylov);
- "Reference" and "List" descriptor parsing is fixed
  (thanks Evgeny Kopylov);
- scalar descriptor values (doubles, floats, booleans) are now returned
  as scalars, not as lists of size 1 (thanks Evgeny Kopylov);
- fixed reading of EngineData past declared length
  (thanks Carlton P. Taylor);
- "background color" Image Resource parsing (thanks Evgeny Kopylov);
- `psd_tools.decoder.actions.Enum.enum` field is renamed to
  `psd_tools.decoder.actions.Enum.value` (thanks Evgeny Kopylov);
- code simplification - constants are now bytestrings as they should be
  (thanks Evgeny Kopylov);
- Python 3.4 is supported.

0.9.1 (2014-03-26)
------------------

- Improved merging of transparent layers (thanks Vladimir Timofeev);
- fixed layer merging and bounding box calculations for empty layers
  (thanks Vladimir Timofeev);
- C extension is rebuilt with Cython 0.20.1.

0.9 (2013-12-03)
----------------

- `psd-tools.py` command-line interface is changed, 'debug' command is added;
- pretty-printing of internal structures;
- pymaging support is fixed;
- allow 'MeSa' to be a signature for image resource blocks
  (thanks Alexey Buzanov);
- `psd_tools.debug.debug_view` utility function is fixed;
- Photoshop CC constants are added;
- Photoshop CC vector origination data is decoded;
- binary data is preserved if descriptor parsing fails;
- more verbose logging for PSD reader;
- channel data reader became more robust - now it doesn't read past
  declared channel length;
- `psd-tools.py --version` command is fixed;
- `lsdk` tagged blocks parsing: this fixes some issues with layer grouping
  (thanks Ivan Maradzhyiski for the bug report and the patch);
- CMYK images support is added (thanks Alexey Buzanov, Guillermo Rauch and
  https://github.com/a-e-m for the help);
- Grayscale images support is added (thanks https://github.com/a-e-m);
- LittleCMS is now optional (but it is still required to get proper colors).

0.8.4 (2013-06-12)
------------------

- Point and Millimeter types are added to UnitFloatType (thanks Doug Ellwanger).

0.8.3 (2013-06-01)
------------------

- Some issues with descriptor parsing are fixed (thanks Luke Petre).

0.8.2 (2013-04-12)
------------------

- Python 2.x: reading data from file-like objects is fixed
  (thanks Pavel Zinovkin).

0.8.1 (2013-03-02)
------------------

- Fixed parsing of layer groups without explicit OPEN_FOLDER mark;
- Cython extension is rebuilt with Cython 0.18.

0.8 (2013-02-26)
----------------

- Descriptor parsing (thanks Oliver Zheng);
- text (as string) is extracted from text layers (thanks Oliver Zheng);
- improved support for optional building of Cython extension.

0.7.1 (2012-12-27)
------------------

- Typo is fixed: ``LayerRecord.cilpping`` should be ``LayerRecord.clipping``.
  Thanks Oliver Zheng.

0.7 (2012-11-08)
----------------

- Highly experimental: basic layer merging is implemented
  (e.g. it is now possible to export layer group to a PIL image);
- ``Layer.visible`` no longer takes group visibility in account;
- ``Layer.visible_global`` is the old ``Layer.visible``;
- ``psd_tools.user_api.combined_bbox`` made public;
- ``Layer.width`` and ``Layer.height`` are removed (use ``layer.bbox.width``
  and ``layer.bbox.height`` instead);
- ``pil_support.composite_image_to_PIL`` is renamed to ``pil_support.extract_composite_image`` and
  ``pil_support.layer_to_PIL`` is renamed to ``pil_support.extract_layer_image``
  in order to have the same API for ``pil_support`` and ``pymaging_support``.

0.6 (2012-11-06)
----------------

- ``psd.composite_image()`` is renamed to ``psd.as_PIL()``;
- Pymaging support: ``psd.as_pymaging()`` and ``layer.as_pymaging()`` methods.


0.5 (2012-11-05)
----------------

- Support for zip and zip-with-prediction compression methods is added;
- support for 16/32bit layers is added;
- optional Cython extension for faster zip-with-prediction decompression;
- other speed improvements.

0.2 (2012-11-04)
----------------

- Initial support for 16bit and 32bit PSD files: ``psd-tools`` v0.2 can
  read composite (merged) images for such files and extract information
  (names, dimensions, hierarchy, etc.) about layers and groups of 16/32bit PSD;
  extracting image data for distinct layers in 16/32bit PSD files is not
  suported yet;
- better ``Layer.__repr__``;
- ``bbox`` property for ``Group``.

0.1.4 (2012-11-01)
------------------

Packaging is fixed in this release.

0.1.3 (2012-11-01)
------------------

- Better support for 32bit images (still incomplete);
- reader is able to handle "global" tagged layer info blocks that
  was previously discarded.

0.1.2 (2012-10-30)
------------------

- warn about 32bit images;
- transparency support for composite images.

0.1.1 (2012-10-29)
------------------

Initial release (v0.1 had packaging issues).
