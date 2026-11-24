use std::env;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let upstream_include = manifest_dir.join("../../vendor/pixelmatch-cpp/include");
    let header = upstream_include.join("mapbox/pixelmatch.hpp");

    // サブモジュール未取得のままだと分かりにくいコンパイルエラーになるため、先に明示的に失敗させる
    if !header.exists() {
        panic!(
            "{} not found. Run `git submodule update --init` first.",
            header.display()
        );
    }

    println!("cargo:rerun-if-changed=shim/shim.cpp");
    println!("cargo:rerun-if-changed=shim/shim.h");
    println!("cargo:rerun-if-changed={}", header.display());

    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap();
    let target_env = env::var("CARGO_CFG_TARGET_ENV").unwrap();
    let static_cxx = target_os == "linux"
        && target_env == "gnu"
        && env::var_os("PIXELMATCH_DYNAMIC_STDCXX").is_none();

    let mut build = cc::Build::new();
    build
        .cpp(true)
        .std("c++17")
        .include(&upstream_include)
        .file("shim/shim.cpp")
        // 差分ピクセル数の JS 版とのビット一致は浮動小数の評価順に依存するため、
        // -ffast-math 等が環境変数経由で混入しても上書きされるよう明示しておく
        .flag_if_supported("-fno-fast-math")
        .warnings(true);

    if static_cxx {
        // libstdc++ を静的リンクし、配布先の libstdc++ のバージョン(GLIBCXX_*)に依存しないようにする。
        // cc の既定は -lstdc++ (動的) なので無効化し、libstdc++.a を明示的にリンクする。
        build.cpp_link_stdlib(None);
    }

    build.compile("pixelmatch_shim");

    if static_cxx {
        let compiler = build.get_compiler();
        let out = Command::new(compiler.path())
            .arg("-print-file-name=libstdc++.a")
            .output()
            .expect("failed to query libstdc++.a location");
        let path = PathBuf::from(String::from_utf8(out.stdout).unwrap().trim());
        let dir = path
            .parent()
            .filter(|d| path.is_absolute() && d.exists())
            .unwrap_or_else(|| {
                panic!(
                    "libstdc++.a not found (got {:?}). Install the static libstdc++ package, \
                     or set PIXELMATCH_DYNAMIC_STDCXX=1 to link it dynamically.",
                    path
                )
            });
        println!("cargo:rustc-link-search=native={}", dir.display());
        println!("cargo:rustc-link-lib=static=stdc++");
    }
    println!("cargo:rerun-if-env-changed=PIXELMATCH_DYNAMIC_STDCXX");
}
