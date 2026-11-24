//! pixelmatch-cpp/test/test.cpp の diffTest と同じケースを、Rust ラッパー経由で検証する。
//! 期待値は上流（JS 版と一致）のものをそのまま使い、ラッパーの受け渡しに欠落がないことを保証する。

use std::fs::File;
use std::path::PathBuf;

use pixelmatch::{Color, Image, Options, pixelmatch};

fn fixture(name: &str) -> (Vec<u8>, usize, usize) {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../vendor/pixelmatch-cpp/test/fixtures")
        .join(format!("{name}.png"));
    let mut decoder = png::Decoder::new(std::io::BufReader::new(File::open(&path).unwrap()));
    // 上流のテストは libpng で RGBA8 に正規化して読むため、同じ変換を指定する
    decoder.set_transformations(
        png::Transformations::normalize_to_color8() | png::Transformations::ALPHA,
    );
    let mut reader = decoder.read_info().unwrap();
    let mut buf = vec![0; reader.output_buffer_size().unwrap()];
    let info = reader.next_frame(&mut buf).unwrap();
    assert_eq!(info.color_type, png::ColorType::Rgba, "{name}");
    buf.truncate(info.buffer_size());
    (buf, info.width as usize, info.height as usize)
}

fn diff_test(
    a: &str,
    b: &str,
    diff: &str,
    options: Options,
    expected: u64,
    ignore_first_half: bool,
) {
    let (d1, w, h) = fixture(a);
    let (d2, w2, h2) = fixture(b);
    assert_eq!((w, h), (w2, h2));

    let mask: Vec<u8> = (0..w * h).map(|i| (i <= w * h / 2) as u8).collect();
    let options = Options {
        ignore_mask: ignore_first_half.then_some(&mask[..]),
        ..options
    };

    let i1 = Image::new(&d1, w, h).unwrap();
    let i2 = Image::new(&d2, w, h).unwrap();
    let mut out = vec![0u8; w * h * 4];
    let n = pixelmatch(&i1, &i2, Some(&mut out), &options).unwrap();
    let n2 = pixelmatch(&i1, &i2, None, &options).unwrap();
    assert_eq!(n, expected, "{a} vs {b}");
    assert_eq!(n, n2);

    let (expected_diff, _, _) = fixture(diff);
    assert!(out == expected_diff, "diff image mismatch: {diff}");
}

fn threshold(t: f64) -> Options<'static> {
    Options {
        threshold: t,
        ..Default::default()
    }
}

#[test]
fn upstream_fixtures() {
    let o = threshold(0.05);
    diff_test("1a", "1b", "1diff", o, 152, false);
    diff_test(
        "1a",
        "1b",
        "1diffdefaultthreshold",
        Options::default(),
        121,
        false,
    );
    diff_test(
        "1a",
        "1b",
        "1diffmask",
        Options {
            diff_mask: true,
            ..o
        },
        152,
        false,
    );
    diff_test(
        "1a",
        "1a",
        "1emptydiffmask",
        Options {
            diff_mask: true,
            ..threshold(0.0)
        },
        0,
        false,
    );
    let colors = Options {
        alpha: 0.5,
        aa_color: Color::new(0, 192, 0),
        diff_color: Color::new(255, 0, 255),
        ..o
    };
    diff_test("2a", "2b", "2diff", colors, 12821, false);
    diff_test("3a", "3b", "3diff", o, 220, false);
    diff_test("4a", "4b", "4diff", o, 36563, false);
    diff_test("5a", "5b", "5diff", o, 0, false);
    diff_test("6a", "6b", "6diff", o, 51, false);
    diff_test("6a", "6a", "6empty", threshold(0.0), 0, false);
    let alt = Options {
        diff_color_alt: Some(Color::new(0, 255, 0)),
        ..Default::default()
    };
    diff_test("7a", "7b", "7diff", alt, 2440, false);
    diff_test("8a", "5b", "8diff", o, 32896, false);
    diff_test("9a", "9b", "9diff", o, 12422, true);
    diff_test("10a", "10b", "10diff", o, 0, true);
}

#[test]
fn stride_matches_packed() {
    let (d1, w, h) = fixture("1a");
    let (d2, _, _) = fixture("1b");
    let pad = 12;
    let padded = |d: &[u8]| -> Vec<u8> {
        d.chunks(w * 4)
            .flat_map(|row| row.iter().copied().chain(std::iter::repeat_n(0xAB, pad)))
            .collect()
    };
    let (p1, p2) = (padded(&d1), padded(&d2));
    let o = threshold(0.05);
    let packed = pixelmatch(
        &Image::new(&d1, w, h).unwrap(),
        &Image::new(&d2, w, h).unwrap(),
        None,
        &o,
    )
    .unwrap();
    let strided = pixelmatch(
        &Image::with_stride(&p1, w, h, w * 4 + pad).unwrap(),
        &Image::with_stride(&p2, w, h, w * 4 + pad).unwrap(),
        None,
        &o,
    )
    .unwrap();
    assert_eq!(packed, strided);
}
