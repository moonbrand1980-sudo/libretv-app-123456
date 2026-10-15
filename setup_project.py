#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LibreTV 安卓投屏版 · 一键生成 Android 工程
==========================================
在 GitHub Actions 中运行本脚本，会在当前目录生成一个完整、可直接编译的
Android WebView 壳工程（内置「投屏菜单」），随后执行

    gradle assembleRelease --no-daemon

即可在 app/build/outputs/apk/release/ 得到**已签名**的 APK。

用法:
    python3 setup_project.py --url https://tv.bagiinlink.eu.org

设计说明:
  * 生成的 App 是一个 WebView 壳，加载 LibreTV 网页版实例（默认官方演示站
    https://tv.bagiinlink.eu.org，访问密码 libretv）。网页版自带「数据源订阅」，
    功能比 Tauri 客户端版更全，且不受 Tauri 壳无法承载 Next.js 的限制。
  * 「投屏」走安卓系统投屏：手机与电视同一 WiFi → 电视开启「投屏接收」→
    手机下拉通知栏点「投屏」。App 内提供投屏设置入口 + 使用说明，
    以及「切换 LibreTV 实例服务器地址」菜单（对应方案里的投屏菜单）。
  * 签名：优先使用仓库根目录的 libretv-cast.jks（固定密钥 → 新版本可覆盖安装）；
    若仓库里没有这个文件，则用 keytool 现场生成一个（每次构建密钥都不同，
    只能全新安装，不能覆盖旧版 —— 仅作兜底）。
"""

import argparse
import os
import subprocess
import sys

DEFAULT_URL = "https://tv.bagiinlink.eu.org"
PKG = "com.libretv.cast"
KS_FILE = "libretv-cast.jks"
STORE_PASS = os.environ.get("KS_STORE_PASS", "LibreTVCast2026")
KEY_ALIAS = os.environ.get("KS_KEY_ALIAS", "libretvcast")

# ---------------------------------------------------------------- Gradle ----

SETTINGS_GRADLE = """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "LibreTV Cast"
include ':app'
"""

ROOT_BUILD_GRADLE = """// 顶层构建脚本
plugins {
    id 'com.android.application' version '8.2.2' apply false
}
"""

GRADLE_PROPERTIES = """org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
org.gradle.parallel=true
android.useAndroidX=true
"""

APP_BUILD_GRADLE = """plugins {
    id 'com.android.application'
}

// 固定签名：使用仓库根目录的 libretv-cast.jks，保证每次构建都能覆盖安装
def ksFile = rootProject.file("__KS_FILE__")
def ksStorePass = System.getenv("KS_STORE_PASS") ?: "__STORE_PASS__"
def ksKeyAlias = System.getenv("KS_KEY_ALIAS") ?: "__KEY_ALIAS__"
def ksKeyPass = System.getenv("KS_KEY_PASS") ?: ksStorePass

android {
    namespace "__PKG__"
    compileSdk 34

    defaultConfig {
        applicationId "__PKG__"
        minSdk 26          // Android 8.0（自适应图标需要 26+）
        targetSdk 34
        versionCode 1
        versionName "1.0.0"
    }

    signingConfigs {
        release {
            storeFile ksFile
            storePassword ksStorePass
            keyAlias ksKeyAlias
            keyPassword ksKeyPass
        }
    }

    buildTypes {
        release {
            minifyEnabled false
            signingConfig signingConfigs.release
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}
"""

# ------------------------------------------------------------- Manifest ----

ANDROID_MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <application
        android:allowBackup="true"
        android:hardwareAccelerated="true"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:label="@string/app_name"
        android:usesCleartextTraffic="true"
        android:theme="@style/AppTheme">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTask"
            android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize|keyboardHidden|uiMode">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""

# ------------------------------------------------------------- Resources ---

STRINGS_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">LibreTV 投屏版</string>
    <string name="default_server_url">__DEFAULT_URL__</string>
    <string name="help_text">投屏三步：\\n1. 手机和电视连同一个 WiFi；\\n2. 电视端打开「投屏 / 多屏互动 / 无线投屏」（各品牌叫法不同）；\\n3. 手机下拉通知栏 → 点「投屏 / Smart View / 无线投屏」→ 选中电视。\\n\\n投屏成功后回到本 App 正常播放即可，画面和声音会走电视。\\n\\n小贴士：\\n· 电视端有浏览器的话，也可以直接在电视上打开当前服务器地址观看；\\n· 投屏时不要锁屏；\\n· 部分电视只支持镜像，画面比例可在播放器里调整。</string>
</resources>
"""

COLORS_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#0B0B0F</color>
    <color name="accent">#00E5C3</color>
</resources>
"""

THEMES_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="@android:style/Theme.Material.Light.NoActionBar">
        <item name="android:windowNoTitle">true</item>
        <item name="android:windowActionBar">false</item>
    </style>
</resources>
"""

ADAPTIVE_ICON_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""

LAUNCHER_FOREGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <!-- 深色底 + 青色圆角电视框 -->
    <path
        android:fillColor="#111318"
        android:pathData="M24,30 h60 a6,6 0 0 1 6,6 v34 a6,6 0 0 1 -6,6 h-60 a6,6 0 0 1 -6,-6 v-34 a6,6 0 0 1 6,-6 z" />
    <path
        android:strokeColor="#00E5C3"
        android:strokeWidth="3"
        android:fillColor="#00000000"
        android:pathData="M24,30 h60 a6,6 0 0 1 6,6 v34 a6,6 0 0 1 -6,6 h-60 a6,6 0 0 1 -6,-6 v-34 a6,6 0 0 1 6,-6 z" />
    <!-- 播放三角 -->
    <path
        android:fillColor="#00E5C3"
        android:pathData="M47,42 L47,64 L66,53 Z" />
    <!-- 底座 -->
    <path
        android:fillColor="#00E5C3"
        android:pathData="M40,80 h28 v3 h-28 z" />
</vector>
"""

# ----------------------------------------------------------------- Java ----

MAIN_ACTIVITY_JAVA = r"""package com.libretv.cast;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

/**
 * LibreTV 投屏版：WebView 壳 + 投屏菜单。
 * 投屏走安卓系统投屏（菜单里一键跳转投屏设置），并支持随时切换 LibreTV 服务器地址。
 */
public class MainActivity extends Activity {

    private static final String PREFS = "cast_prefs";
    private static final String KEY_URL = "server_url";

    private FrameLayout root;
    private WebView web;
    private View customView;
    private WebChromeClient.CustomViewCallback customCb;
    private String serverUrl;
    private SharedPreferences prefs;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String defaultUrl = getString(R.string.default_server_url);
        serverUrl = prefs.getString(KEY_URL, defaultUrl);

        root = new FrameLayout(this);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setSupportZoom(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return false; // 全部在应用内打开
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onShowCustomView(View view, CustomViewCallback callback) {
                if (customView != null) {
                    callback.onCustomViewHidden();
                    return;
                }
                customView = view;
                customCb = callback;
                web.setVisibility(View.GONE);
                root.addView(view, new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
                enterImmersive();
            }

            @Override
            public void onHideCustomView() {
                exitCustomView();
            }
        });

        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // 悬浮「投屏」按钮
        Button castBtn = new Button(this);
        castBtn.setText("投屏");
        FrameLayout.LayoutParams bp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bp.gravity = Gravity.BOTTOM | Gravity.END;
        bp.rightMargin = dp(16);
        bp.bottomMargin = dp(28);
        root.addView(castBtn, bp);
        castBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showCastMenu();
            }
        });

        setContentView(root);

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(serverUrl);
        }
    }

    /** 投屏菜单：系统投屏入口 / 切换服务器 / 刷新 / 清缓存 / 说明 */
    private void showCastMenu() {
        final String[] items = new String[]{
                "📺 打开系统投屏设置（推荐）",
                "🔗 切换 LibreTV 服务器地址",
                "🔄 刷新页面",
                "🧹 清除缓存",
                "❓ 投屏使用说明"
        };
        new AlertDialog.Builder(this)
                .setTitle("投屏菜单")
                .setItems(items, (dialog, which) -> {
                    switch (which) {
                        case 0:
                            openSystemCastSettings();
                            break;
                        case 1:
                            promptServerUrl();
                            break;
                        case 2:
                            web.reload();
                            break;
                        case 3:
                            web.clearCache(true);
                            toast("已清除缓存");
                            break;
                        default:
                            showHelp();
                            break;
                    }
                })
                .setNegativeButton("关闭", null)
                .show();
    }

    /** 一键跳转系统投屏设置页（各品牌 ROM 都会映射到各自的投屏/多屏互动页面） */
    private void openSystemCastSettings() {
        try {
            startActivity(new Intent("android.settings.CAST_SETTINGS"));
        } catch (Exception e) {
            try {
                startActivity(new Intent(android.provider.Settings.ACTION_WIRELESS_SETTINGS));
            } catch (Exception e2) {
                toast("未找到投屏设置，请下拉通知栏使用「投屏 / Smart View」");
            }
        }
    }

    /** 切换 LibreTV 实例服务器地址（保存在本地，下次启动继续用） */
    private void promptServerUrl() {
        final EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setText(serverUrl);
        new AlertDialog.Builder(this)
                .setTitle("切换 LibreTV 服务器地址")
                .setMessage("输入完整地址，例如：\nhttps://tv.bagiinlink.eu.org")
                .setView(input)
                .setPositiveButton("确定", (dialog, which) -> {
                    String u = input.getText().toString().trim();
                    if (u.length() == 0) {
                        return;
                    }
                    if (!u.startsWith("http://") && !u.startsWith("https://")) {
                        u = "https://" + u;
                    }
                    serverUrl = u;
                    prefs.edit().putString(KEY_URL, u).apply();
                    web.loadUrl(u);
                    toast("已切换到 " + u);
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showHelp() {
        new AlertDialog.Builder(this)
                .setTitle("投屏使用说明")
                .setMessage(getString(R.string.help_text))
                .setPositiveButton("知道了", null)
                .show();
    }

    private void exitCustomView() {
        if (customView == null) {
            return;
        }
        root.removeView(customView);
        customView = null;
        if (customCb != null) {
            customCb.onCustomViewHidden();
            customCb = null;
        }
        web.setVisibility(View.VISIBLE);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
    }

    private void enterImmersive() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onBackPressed() {
        if (customView != null) {
            exitCustomView();
            return;
        }
        if (web.canGoBack()) {
            web.goBack();
            return;
        }
        new AlertDialog.Builder(this)
                .setMessage("退出 LibreTV 投屏版？")
                .setPositiveButton("退出", (dialog, which) -> finish())
                .setNegativeButton("取消", null)
                .show();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }
}
"""

# ---------------------------------------------------------------- writer ---


def write(path: str, content: str) -> None:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("  生成", os.path.relpath(path))


def ensure_keystore() -> None:
    """优先用仓库里固定的 jks；没有就用 keytool 现场生成一个兜底。"""
    if os.path.isfile(KS_FILE):
        print("  使用仓库自带签名密钥:", KS_FILE)
        return
    print("  !! 未找到 %s，尝试用 keytool 现场生成（每次构建密钥不同，仅测试用）" % KS_FILE)
    java_home = os.environ.get("JAVA_HOME", "")
    keytool = os.path.join(java_home, "bin", "keytool") if java_home else "keytool"
    cmd = [
        keytool, "-genkeypair",
        "-keystore", KS_FILE,
        "-storepass", STORE_PASS,
        "-keypass", STORE_PASS,
        "-alias", KEY_ALIAS,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "36500",
        "-dname", "CN=LibreTV Cast, O=LibreTV",
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("  已生成临时签名密钥:", KS_FILE)
    except Exception as e:  # noqa: BLE001
        sys.exit("[setup_project] 生成签名密钥失败：%s\n请确认已安装 JDK 17（keytool 可用）" % e)


def main() -> None:
    ap = argparse.ArgumentParser(description="一键生成 LibreTV 安卓投屏版工程")
    ap.add_argument("--url", default=DEFAULT_URL, help="内置的 LibreTV 网页版实例地址")
    args = ap.parse_args()
    url = args.url.strip() or DEFAULT_URL

    print("[setup_project] 目标实例:", url)

    # ---- Java / Gradle 工程 -------------------------------------------------
    write("settings.gradle", SETTINGS_GRADLE)
    write("build.gradle", ROOT_BUILD_GRADLE)
    write("gradle.properties", GRADLE_PROPERTIES)
    write(
        "app/build.gradle",
        (APP_BUILD_GRADLE
         .replace("__KS_FILE__", KS_FILE)
         .replace("__STORE_PASS__", STORE_PASS)
         .replace("__KEY_ALIAS__", KEY_ALIAS)
         .replace("__PKG__", PKG)),
    )

    java_dir = os.path.join("app/src/main/java", *PKG.split("."))
    write(os.path.join(java_dir, "MainActivity.java"),
          MAIN_ACTIVITY_JAVA.replace("__PKG__", PKG))

    # ---- 资源 ---------------------------------------------------------------
    write("app/src/main/AndroidManifest.xml", ANDROID_MANIFEST)
    write("app/src/main/res/values/strings.xml",
          STRINGS_XML.replace("__DEFAULT_URL__", url))
    write("app/src/main/res/values/colors.xml", COLORS_XML)
    write("app/src/main/res/values/themes.xml", THEMES_XML)
    write("app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml", ADAPTIVE_ICON_XML)
    write("app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml", ADAPTIVE_ICON_XML)
    write("app/src/main/res/drawable/ic_launcher_foreground.xml", LAUNCHER_FOREGROUND_XML)

    # ---- 签名 ---------------------------------------------------------------
    ensure_keystore()

    print()
    print("[setup_project] 工程生成完毕 ✅")
    print("  下一步: gradle assembleRelease --no-daemon")
    print("  产物  : app/build/outputs/apk/release/app-release.apk")


if __name__ == "__main__":
    main()
