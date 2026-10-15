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
        versionCode 7
        versionName "1.4.1"
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
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />

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
    <string name="help_text">直连投屏流程：\\n1. 手机和电视连同一个 WiFi；\\n2. 在本 App 播放视频，播放器控制条右侧会出现「投屏」按钮；\\n3. 点「投屏」→ 自动搜索局域网电视（海信 / 小米 / TCL / 当贝等 DLNA 设备）→ 选中电视即开始播放，无需任何第三方软件。\\n\\n说明：\\n· 长按「投屏」按钮可打开功能菜单（切换服务器 / 横竖屏 / 清缓存等）；\\n· 搜不到电视时，确认电视已开启「DLNA / 多屏互动 / 投屏」开关（各品牌叫法不同）；\\n· 也可以选「用其他应用播放」，交给 VLC / Web Video Caster；\\n· 投屏开始后可锁屏或退出本 App，电视独立播放。\\n\\n· 投屏时手机和电视请勿开热点隔离或访客网络。\\n\\n影片筛选：\\n· 非播放页右下角有「筛选」悬浮键 → 全屏浏览页：电影/剧集切换、类型/地区/年份筛选行、海报墙上滑自动加载；\\n· 顶部搜索框可直搜片名；点海报自动找片源播放；\\n· 点右上「设为启动页」后，每次打开 App 直接进入筛选页；\\n· 筛选使用本站豆瓣接口，若为空请先在本站登录。</string>
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

# 官方 LibreTV 图标（来自 Vayne-bit/LibreTV-App 官方仓库，5 密度 launcher + round）
OFFICIAL_ICONS_B64 = {
    "mipmap-mdpi/ic_launcher.png":
        "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAADt0lEQVR4nO2YPWhkVRTH/+fc+95mUEGQBC1WWYMpRsKEmSHFNgN2"
        "EbTyFbKgbLGNi4KVYLdYiPa7lY2FsHDXRkFLO4vsm4ybwLBENkGtTGE1a/TNu+dY5E3ITt5MMh8PN/B+5btf//+5992PA5SUlJSU"
        "lFxgaIo2HEXRNO3OxDmnAKSIvhFFkcF0hieFsrHOV3mCOgoAzWbzVaS4LCILRKTTKBxGVYmZ/4HFH3Ec7+WNe5a4ceUKAPVa/RoT"
        "31RonZkvzSY5HxH5l0BbpHT7/oP73wxrGCVwbFmj0aiQ0NeGzTuiAhEBilqnADMzmBipT7+FwXvtdvswK8s1McoARVHEAPBo99H3"
        "YRBu9Pv9vkKZiHhMu1lRVRUCSRAEQdJPflxeWX4LAJxzghwTnNdLFEXsnPN7u3sfhUG4kaRJAkJAREX/yEREBoQgSZMkDMKN/d39"
        "D51zfhDQUw1GfatWq88sBAu/MvOSqgIjzOYwiNKsRoWIoKJ/HvYPV7rd7uOh/pErKnOqlaBy1RjzYrbmzyseOBJOquqnVT7QJiJg"
        "wy9VgspVAJo3C6c+HBwcUCZjlYknPlhU9RCAWmtNZmKWH16YWEFYfULbCUZGVqHPYoJloKqpNRYEugOPpoj8ZK01zMyqmuKM/XwM"
        "lGnJZZKlcT4Yf7d32ltxJ35DRN5V1YeBDSwRzWNZ5Qw3Z1SVAXC1Wg3jTnw38UnTe/8pgL+stQZHMzGXExwoYgaOkMXFRYmiyGxv"
        "bz+Of4k/9/B1EfmKMjAnE0UZAAA45zwAarVattPp/BZ34hvwWIXi4ZGH2U/0Qg0MWFpaOo62N/45EM592zyLwgz0ej1qtVoWgDrn"
        "/NraWq2x1rhnyf5MoNcmPBxHYmdWOoSqUhRFpuqq/hZuSfP15mUN9RMC3WDm0HsvyA67eYw3dwNElDjnfK1We77BjZsK/diyfSH1"
        "KdI09dl9am7M0wApFAR6pV6rX2PmzwybK148+mk/JSIzb/HAGAME6mGCrY6IjPceRHTdsLmuUPTTviciJqJZAqWZllxOdXy8Yyh2"
        "RIUw4Y+mqppKKtl2P2vEWVQIip0ntJ2giOv0vJjuOo3s2trtdnsM/sIaywDSwuUOi4Cm1lhW6Jfdbrc3uOYP1zvPk/K7MAjf/J+e"
        "lD8sryy/DYx+Uj61j3ov/p6yvj/to/5k+XFaxbD5QFQaRadVROX21oOtmdMqw3UUANbX169IIi8XkdjikH/f3Nzczxt3Zi5yanGY"
        "i5ncLSkpKSkpeRr5D3P0xqosAIonAAAAAElFTkSuQmCC"
        ,
    "mipmap-mdpi/ic_launcher_round.png":
        "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAADR0lEQVR4nOWaTW7bSBCFv2qSQnwA+wIBZqFZyLAEb3UKHijn4U0c"
        "Kpp4AC4MJNl7bSAAye7KgqEii79SmpIz8wAJhNTNeq9ZVV1doOAfOmKM+DLm40ZjCA/hZB6/I8AH8UMczecUAVMQP8RoXubIG5+D"
        "/FF2xio9F/E29HIc8wQuSX7Q/pCAS5Ov0cmjT8BbIV+jlU+Xf/WSj+P4t9m0IUmSMcNGxa0efuI4bvw21WfA1qCa3tVfrVZQgnMO"
        "ET8VgapijIEQ0jQdM0UaF/W9umbcLe4wYlB+GpsAzjkEQVT4+Pnj0HDZfe2hIWC5XCJOCEyAU4dzzhPddhhjMGIobQkBbDabrqEN"
        "Aa/I14H65ekLs2hGURQo6s1tuqCqCEIUReRFzvu/3gOdAS6tvhDHMUmS8PXpK7NoRl7mIExOHn7aEMjLnFk049vTN5Ik6cx8NaOG"
        "68znc95F7zDGoHqZLUFEUKd8L76TZVnrmMYTqJVeRVcEQXCyz/sQ7ZzDBIar6OoVt300BDw/P1cXAqbdw3pREw/D0IsII2bnJztu"
        "+/93EjmyklBVwiBEELDV6oVh6MUF+7gYfNc8Bjb/bki3Kc45VJUojCp/niCWvO9INcn5fE66TcltjrUWqNzKN6bZUoHr62viOObx"
        "8ZH0nxSL3ZUfPtPxZALg1+azXq/Zbrek2xQsoP72lEkF1Li5udld28B67ApNKODl5YX1eg1UT+L29pbl7ZJQqkzlK6C9R5WqEscx"
        "82TOBz6w+nuFzqr6xhizC2hf8C5AREiShMViwdIsUZTQhJS2pCxL7/WUVxdSqpW+W9wRmYjQVO5SlAUwTTEYUoVUy1HtOGMigrUW"
        "kersoChFWXhJm31cGi60yxgKTo8v5FSV0pXe8r1Tt1ve/WxW479XTkNVtmZZhsEQBv63/zFQquJQUbIsGzzQVHP28KccKTsF1LjU"
        "od46ixrtO9TDgQAYaKvUIqZuqzh1fPr8aWj4uLbKIe7v73G5m6SxZWaGh4eHsdM6jZ/S7jtna/HVIv/xzd2TBFwYrzh3ReP0HazT"
        "0ODVl07emohWPkP58K2I6OQxJqFfWkSv/WPJnTO4R3E7dks919MYbed/+a7EIS76tsoPjXOoEaZD4SgAAAAASUVORK5CYII="
        ,
    "mipmap-hdpi/ic_launcher.png":
        "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"
        ,
    "mipmap-hdpi/ic_launcher_round.png":
        "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"
        ,
    "mipmap-xhdpi/ic_launcher.png":
        "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"
        ,
    "mipmap-xhdpi/ic_launcher_round.png":
        "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"
        ,
    "mipmap-xxhdpi/ic_launcher.png":
        "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"
        ,
    "mipmap-xxhdpi/ic_launcher_round.png":
        "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"
        ,
    "mipmap-xxxhdpi/ic_launcher.png":
        "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAQJ0lEQVR4nO3df4wd1XUH8O+5d956Tc2vVl2kFCFVokq69a7felaL"
        "KSWrqm2I0jaJVAZaNZUqVZRAIGpSKYFQQKSVQtQmqhQCIVUbqU2lwMsfKWrUplH/eGpRDN7ZfW9NFiJolCLyR5dU2MWA7bn3nP7x"
        "Zp7XFr/xmzfv+fuRzJOXt5rrmXNm7rlz5w5ARERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERE"
        "RERERERERERERERERERERERvhoy7ASMiZ3zSO2NnfE6NaQgQybLMbW9vy9zcnHU6HcUUHqiGmLp9PakJIFmWuU6nYwD0zP85Pz+/"
        "53x3/k/F2TgTY3RjaN/U8N6rP+5PvqgvvrS1tXXsVb7iVldXXbfbVbzKsWi6SUsAlyGTDjqx+sHevXsv2ZXsSmFYMljbibvMYHMG"
        "u0BMZk3Mj7PBk05MookdF8hRgTyvps86cRsG6xVarG1ubm5X382yzM935u0e3DMxiTApCVCdxRUAFhYWLp1JZn4Lig9BcMA5d5ET"
        "B4PBbPAHAGCATfYVeuwEMowSERn8gUBNoaovAHgMgm/D4ZE8z58tf+2049VkTU+AqqsTAWD/wv4DSHCTmHzQe38RAKgqzEzNTDE8"
        "XiJo/r9t0pjBqvOJiYgTEefcINY16lGFPiImD+b9/FFgcEVoep3Q2CDJkPmqq9Nut/d58XcI5FrnnKgqVDUCgIg4NPjfMeWsPPHA"
        "Oeedc1BVM9g3EXBvfjhfB04/lk3TyMApzxxxZWXlAi30LgC3OudmYowws8igbyQzMxUR570XjVoAuK+w4rP9fv9IdUzH3cgzNS2I"
        "hl2epaWl93r4+733vxRCqAKfBe0EqI5VkiQIMfwgFvHG3hO9bhO7RE1KgKottn/f/j9xzv2ViPgYYygDv0ltpTdmZha994mZBTO7"
        "Le/lX8CO4zzOxlWaElTDO7fL7eX7vfc3hhjMzKzs7tDkUgCS+ERCDF/Ne/lNaNCd5SYkgADA6uqqP3b02NeTJLm+KAqe9aeLmVls"
        "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"
        ,
    "mipmap-xxxhdpi/ic_launcher_round.png":
        "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"
        ,
}

MAIN_ACTIVITY_JAVA = r"""package com.libretv.cast;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.util.Xml;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

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
    private volatile String lastMediaUrl;
    private String serverUrl;
    private SharedPreferences prefs;

    // ---- DLNA 直连投屏状态 ----
    private String activeCastName;
    private String activeCastControlUrl;
    private WifiManager.MulticastLock multicastLock;

    // ---- 全屏时保存的原状态栏颜色（退出时还原） ----
    private int savedStatusBarColor = Integer.MIN_VALUE;
    private int savedNavBarColor = Integer.MIN_VALUE;

    /** 从页面里抓当前视频的真实直链（ArtPlayer / hls.js / 原生 video 逐级尝试） */
    private static final String JS_EXTRACT_VIDEO =
            "(function(){function http(u){return (u && /^https?:/i.test(u)) ? u : '';}"
            + "try{if(window.art&&window.art.video){var a=http(window.art.video.src||window.art.video.currentSrc);if(a)return a;}}catch(e){}"
            + "try{if(window.hls&&window.hls.url){var h=http(window.hls.url);if(h)return h;}}catch(e){}"
            + "try{var vs=document.querySelectorAll('video');for(var i=0;i<vs.length;i++){var v=vs[i];var u=http(v.currentSrc||v.src);if(u)return u;}"
            + "var s=document.querySelector('video source');if(s){var su=http(s.src);if(su)return su;}}catch(e){}"
            + "return '';})()";

    /** 注入网页的「投屏」按钮：只有视频出现时才有；绝对定位在播放器容器右下（控制条上方），横竖屏自动跟随 */
    private static final String JS_INJECT_BUTTON =
            "(function(){"
            + "if(window.__ltvCastTimer){return;}"
            + "window.__ltvCastTimer=setInterval(function(){try{"
            + "var v=document.querySelector('video');"
            + "var btn=document.getElementById('__ltv_cast');"
            + "if(!v){if(btn&&btn.parentNode){btn.parentNode.removeChild(btn);}return;}"
            + "var host=document.querySelector('.art-video-player')||v.parentElement||document.body;"
            + "if(!btn){"
            + "btn=document.createElement('button');"
            + "btn.id='__ltv_cast';btn.textContent='投屏';"
            + "btn.__base='padding:5px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.4);background:rgba(0,0,0,.55);color:#fff;font-size:12px;line-height:1.4;cursor:pointer;';"
            + "var pressT=null,moved=false,px=0,py=0;"
            + "btn.addEventListener('touchstart',function(e){e.stopPropagation();var t=e.touches[0];px=t.clientX;py=t.clientY;moved=false;"
            + "pressT=setTimeout(function(){pressT=null;try{window.AndroidBridge.openMenu();}catch(err){}},650);},{passive:true});"
            + "btn.addEventListener('touchmove',function(e){e.stopPropagation();var t=e.touches[0];"
            + "if(Math.abs(t.clientX-px)>12||Math.abs(t.clientY-py)>12){moved=true;if(pressT){clearTimeout(pressT);pressT=null;}}},{passive:true});"
            + "btn.addEventListener('touchend',function(e){e.stopPropagation();if(pressT){clearTimeout(pressT);pressT=null;}"
            + "if(!moved){try{window.AndroidBridge.smartCast();}catch(err){}}},{passive:true});"
            + "btn.addEventListener('click',function(e){e.stopPropagation();e.preventDefault();try{window.AndroidBridge.smartCast();}catch(err){}});"
            + "}"
            + "if(btn.parentNode!==host){"
            + "host.appendChild(btn);"
            + "if(getComputedStyle(host).position==='static'){host.style.position='relative';}"
            + "btn.style.cssText=btn.__base+'position:absolute;right:10px;bottom:58px;z-index:99999;';"
            + "}"
            + "}catch(e){}},900);})()";

    /** 注入网页的「筛选」首页：OK猫影视风格全屏浏览页（类别 + 类型/地区/年份 + 海报墙 + 滚动加载 + 站内搜索 + 可设启动页）。 */
    private static final String JS_INJECT_FILTER =
            "(function(){"
            + "if(window.__ltvFilterInit){return;}"
            + "window.__ltvFilterInit=1;"
            + "var CONF={"
            + "movie:{'类型':['热门','最新','经典','豆瓣高分','冷门佳片','动作','喜剧','爱情','科幻','悬疑','恐怖','治愈','动画','纪录片'],"
            + "'地区':['华语','欧美','韩国','日本'],"
            + "'年份':['2026','2025','2024','2023','2022','2021','2020','2019','2018']},"
            + "tv:{'类型':['热门','最新','经典','豆瓣高分','综艺','纪录片','日本动画'],"
            + "'地区':['美剧','英剧','韩剧','日剧','国产剧','港剧'],"
            + "'年份':['2026','2025','2024','2023','2022','2021','2020','2019','2018']}"
            + "};"
            + "var curType='movie',curTag='热门',pageStart=0,loading=false,hasMore=true,mode='filter';"
            + "function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');}"
            + "function videoOn(){return !!document.querySelector('video');}"
            + "setInterval(function(){"
            + "var f=document.getElementById('__ltv_filter');"
            + "if(videoOn()){if(f&&f.parentNode){f.parentNode.removeChild(f);}return;}"
            + "if(!document.body||f){return;}"
            + "f=document.createElement('button');f.id='__ltv_filter';f.textContent='筛选';"
            + "f.style.cssText='position:fixed;right:14px;bottom:24px;z-index:99998;padding:6px 14px;border-radius:16px;border:1px solid rgba(255,255,255,.35);background:rgba(18,18,26,.75);color:#fff;font-size:13px;cursor:pointer;';"
            + "f.addEventListener('click',function(e){e.stopPropagation();openPanel();});"
            + "document.body.appendChild(f);"
            + "},900);"
            + "function openPanel(){"
            + "if(document.getElementById('__ltv_ovl')){return;}"
            + "var ovl=document.createElement('div');ovl.id='__ltv_ovl';"
            + "ovl.style.cssText='position:fixed;inset:0;z-index:99999;background:#0f0f16;overflow-y:auto;-webkit-overflow-scrolling:touch;';"
            + "document.body.appendChild(ovl);"
            + "var head=document.createElement('div');"
            + "head.style.cssText='position:sticky;top:0;background:#14141e;border-bottom:1px solid #26263a;padding:10px 12px;z-index:2;';"
            + "ovl.appendChild(head);"
            + "var grid=document.createElement('div');"
            + "grid.style.cssText='display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:12px;';"
            + "ovl.appendChild(grid);"
            + "var tip=document.createElement('div');"
            + "tip.style.cssText='color:#8a8aa0;font-size:12px;text-align:center;padding:14px;';"
            + "ovl.appendChild(tip);"
            + "ovl.addEventListener('scroll',function(){"
            + "if(mode!=='filter'||loading||!hasMore){return;}"
            + "if(ovl.scrollTop+ovl.clientHeight>=ovl.scrollHeight-500){loadPage(true);}"
            + "});"
            + "buildHead(head);buildFilters(head);resetLoad();"
            + "}"
            + "function buildHead(head){"
            + "var r1=document.createElement('div');"
            + "r1.style.cssText='display:flex;align-items:center;gap:8px;';"
            + "var close=document.createElement('button');close.textContent='\\u2715';"
            + "close.style.cssText='background:none;border:none;color:#999;font-size:20px;cursor:pointer;padding:0 4px;';"
            + "close.addEventListener('click',function(){var o=document.getElementById('__ltv_ovl');if(o){o.remove();}});"
            + "r1.appendChild(close);"
            + "var title=document.createElement('span');"
            + "title.textContent='\\uD83C\\uDFAC 影片筛选';"
            + "title.style.cssText='color:#fff;font-size:16px;font-weight:600;flex:1;';"
            + "r1.appendChild(title);"
            + "var auto=document.createElement('button');"
            + "var isAuto=false;try{isAuto=localStorage.getItem('__ltvAutoFilter')==='1';}catch(e){}"
            + "auto.textContent=isAuto?'\\u2605 启动页':'设为启动页';"
            + "auto.style.cssText='padding:4px 10px;border-radius:12px;font-size:11px;cursor:pointer;border:1px solid '+(isAuto?'#e91e63':'#333')+';background:'+(isAuto?'#e91e63':'#1e1e2c')+';color:#bbb;';"
            + "auto.addEventListener('click',function(){"
            + "var on=false;"
            + "try{on=localStorage.getItem('__ltvAutoFilter')==='1';"
            + "if(on){localStorage.removeItem('__ltvAutoFilter');}else{localStorage.setItem('__ltvAutoFilter','1');}}catch(e){on=!on;}"
            + "auto.textContent=on?'\\u2605 启动页':'设为启动页';"
            + "auto.style.border=on?'1px solid #e91e63':'1px solid #333';"
            + "auto.style.background=on?'#e91e63':'#1e1e2c';"
            + "});"
            + "r1.appendChild(auto);head.appendChild(r1);"
            + "var tabs=document.createElement('div');tabs.style.cssText='display:flex;gap:8px;margin-top:10px;';"
            + "[['movie','电影'],['tv','剧集']].forEach(function(pr){"
            + "var b=document.createElement('button');b.textContent=pr[1];var on=curType===pr[0];"
            + "b.style.cssText='flex:1;padding:9px;border-radius:8px;font-size:14px;cursor:pointer;border:none;background:'+(on?'#e91e63':'#1e1e2c')+';color:'+(on?'#fff':'#bbb')+';';"
            + "b.addEventListener('click',function(){if(curType!==pr[0]){curType=pr[0];curTag='热门';buildFilters(head);resetLoad();}});"
            + "tabs.appendChild(b);"
            + "});"
            + "head.appendChild(tabs);"
            + "var sr=document.createElement('div');sr.style.cssText='display:flex;gap:8px;margin-top:10px;';"
            + "var inp=document.createElement('input');inp.placeholder='搜索片名…';"
            + "inp.style.cssText='flex:1;padding:8px 12px;border-radius:8px;border:1px solid #2a2a3a;background:#1e1e2c;color:#fff;font-size:13px;outline:none;';"
            + "var sb=document.createElement('button');sb.textContent='搜索';"
            + "sb.style.cssText='padding:8px 16px;border-radius:8px;border:none;background:#e91e63;color:#fff;font-size:13px;cursor:pointer;';"
            + "function doSearchClick(){var q=(inp.value||'').trim();if(q){mode='search';hasMore=false;searchGrid(q);}}"
            + "sb.addEventListener('click',doSearchClick);"
            + "inp.addEventListener('keydown',function(e){if(e.key==='Enter'){doSearchClick();}});"
            + "sr.appendChild(inp);sr.appendChild(sb);head.appendChild(sr);"
            + "}"
            + "function buildFilters(head){"
            + "var old=document.getElementById('__ltv_frows');if(old&&old.parentNode){old.parentNode.removeChild(old);}"
            + "var box=document.createElement('div');box.id='__ltv_frows';"
            + "box.style.cssText='margin-top:10px;';"
            + "var conf=CONF[curType];"
            + "Object.keys(conf).forEach(function(rowName){"
            + "var row=document.createElement('div');"
            + "row.style.cssText='display:flex;gap:6px;align-items:flex-start;margin:6px 0;';"
            + "var lab=document.createElement('span');lab.textContent=rowName;"
            + "lab.style.cssText='color:#8a8aa0;font-size:12px;min-width:34px;line-height:26px;';"
            + "row.appendChild(lab);"
            + "var wrap=document.createElement('div');"
            + "wrap.style.cssText='display:flex;gap:6px;overflow-x:auto;white-space:nowrap;padding-bottom:2px;';"
            + "conf[rowName].forEach(function(t){"
            + "var on=(t===curTag);"
            + "var b=document.createElement('button');b.textContent=t;"
            + "b.style.cssText='flex:0 0 auto;padding:4px 12px;border-radius:13px;font-size:12px;cursor:pointer;border:1px solid '+(on?'#e91e63':'#333')+';background:'+(on?'#e91e63':'#1e1e2c')+';color:'+(on?'#fff':'#bbb')+';';"
            + "b.addEventListener('click',function(){curTag=t;mode='filter';buildFilters(head);resetLoad();});"
            + "wrap.appendChild(b);"
            + "});"
            + "row.appendChild(wrap);box.appendChild(row);"
            + "});"
            + "head.appendChild(box);"
            + "}"
            + "function ovlParts(){"
            + "var ovl=document.getElementById('__ltv_ovl');"
            + "if(!ovl){return null;}"
            + "var divs=ovl.children;"
            + "return {grid:divs[1],tip:divs[2]};"
            + "}"
            + "function resetLoad(){pageStart=0;hasMore=true;loadPage(false);}"
            + "function loadPage(append){"
            + "if(loading){return;}loading=true;"
            + "var p=ovlParts();"
            + "if(!p){loading=false;return;}"
            + "if(!append){p.grid.innerHTML='';}"
            + "p.tip.textContent='加载中…';"
            + "var url='/api/douban?type='+encodeURIComponent(curType)+'&tag='+encodeURIComponent(curTag)+'&pageStart='+pageStart+'&pageSize=24';"
            + "fetch(url,{credentials:'include'}).then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.list||d.subjects||d.items||d.data))||[];"
            + "if(!Array.isArray(list)){list=[];}"
            + "if(!append){p.grid.innerHTML='';}"
            + "if(!list.length){hasMore=false;p.tip.textContent=append?'没有更多了':'暂无内容（若一直为空，请先在本站登录）';loading=false;return;}"
            + "list.forEach(function(it){p.grid.appendChild(makeCard(it));});"
            + "hasMore=list.length>=24;"
            + "p.tip.textContent=hasMore?'上滑加载更多':'没有更多了';"
            + "pageStart+=list.length;loading=false;"
            + "}).catch(function(e){loading=false;p.tip.textContent='加载失败：'+esc(e.message||e);});"
            + "}"
            + "function makeCard(it){"
            + "var t=it.title||it.name||'';"
            + "var img=it.poster||it.cover||it.img||'';"
            + "if(img){img=img.replace(/img\\d+\\.doubanio\\.com/g,'img.doubanio.cmliussss.net');}"
            + "var rate=it.rate||it.rating||'';"
            + "var card=document.createElement('div');card.style.cssText='cursor:pointer;';"
            + "card.innerHTML='<div style=\"position:relative\"><img src=\"'+esc(img)+'\" loading=\"lazy\" style=\"width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:8px;background:#222\">'"
            + "+(rate?'<span style=\"position:absolute;right:4px;top:4px;background:rgba(0,0,0,.7);color:#f5c518;font-size:11px;padding:1px 4px;border-radius:4px\">\\u2605'+esc(rate)+'</span>':'')+'</div>'"
            + "+'<div style=\"color:#ddd;font-size:12px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+esc(t)+'</div>';"
            + "card.addEventListener('click',function(){playTitle(t);});"
            + "return card;"
            + "}"
            + "function searchGrid(q){"
            + "var p=ovlParts();if(!p){return;}"
            + "p.grid.innerHTML='';p.tip.textContent='搜索中…';"
            + "fetch('/api/search',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})})"
            + ".then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.regular_results||d.results||d.list||d.data))||[];"
            + "if(!Array.isArray(list)){list=[];}"
            + "if(!list.length){p.tip.textContent='未找到「'+q+'」的片源';return;}"
            + "p.tip.textContent='找到 '+list.length+' 个结果';"
            + "list.forEach(function(it){"
            + "var src=it.source||it.sourceKey||'';var id=it.vod_id||it.id||'';"
            + "var t=it.vod_name||it.title||q;"
            + "var img=it.vod_pic||it.pic||it.cover||'';"
            + "var sn=it.source_name||'';"
            + "var card=document.createElement('div');card.style.cssText='cursor:pointer;';"
            + "card.innerHTML='<div style=\"position:relative\"><img src=\"'+esc(img)+'\" loading=\"lazy\" style=\"width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:8px;background:#222\">'"
            + "+(sn?'<span style=\"position:absolute;left:4px;top:4px;background:rgba(233,30,99,.85);color:#fff;font-size:10px;padding:1px 5px;border-radius:4px\">'+esc(sn)+'</span>':'')+'</div>'"
            + "+'<div style=\"color:#ddd;font-size:12px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+esc(t)+'</div>';"
            + "card.addEventListener('click',function(){if(src&&id){watch(src,id,t);}});"
            + "p.grid.appendChild(card);"
            + "});"
            + "}).catch(function(e){p.tip.textContent='搜索失败：'+esc(e.message||e);});"
            + "}"
            + "function playTitle(title){"
            + "if(!title){return;}"
            + "var p=ovlParts();"
            + "if(p){p.tip.textContent='正在找片源：'+title;}"
            + "fetch('/api/search',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:title})})"
            + ".then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.regular_results||d.results||d.list||d.data))||[];"
            + "if(!Array.isArray(list)){list=[];}"
            + "var hit=null;"
            + "for(var i=0;i<list.length;i++){"
            + "var it=list[i];var src=it.source||it.sourceKey||'';var id=it.vod_id||it.id||'';"
            + "if(src&&id){hit=it;break;}"
            + "}"
            + "if(!hit){if(p){p.tip.textContent='未找到可播放的片源：'+title;}return;}"
            + "var src=hit.source||hit.sourceKey||'';var id=hit.vod_id||hit.id||'';"
            + "var t=hit.vod_name||hit.title||title;"
            + "watch(src,id,t);"
            + "}).catch(function(e){if(p){p.tip.textContent='搜索失败：'+esc(e.message||e);}});"
            + "}"
            + "function watch(src,id,t){"
            + "var ovl=document.getElementById('__ltv_ovl');if(ovl){ovl.remove();}"
            + "location.href='/watch?source='+encodeURIComponent(src)+'&id='+encodeURIComponent(id)+'&title='+encodeURIComponent(t);"
            + "}"
            + "try{if(localStorage.getItem('__ltvAutoFilter')==='1'&&!videoOn()&&(location.pathname==='/'||location.pathname==='/index.html')){openPanel();}}catch(e){}"
            + "})()";

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

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                // 记录页面加载过的视频直链（hls.js 播放时 video.src 是 blob:，只能从这里抓）
                String u = request.getUrl().toString();
                if (isMediaUrl(u)) {
                    lastMediaUrl = u;
                }
                return null;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                // 每次页面加载完：注入跟随视频出现的「投屏」按钮 + 「筛选」功能
                view.evaluateJavascript(JS_INJECT_BUTTON, null);
                view.evaluateJavascript(JS_INJECT_FILTER, null);
            }
        });
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");
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
                // 视频全屏时自动横屏
                setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                enterImmersive();
            }

            @Override
            public void onHideCustomView() {
                exitCustomView();
            }
        });

        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

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
                "🚀 投屏当前视频（搜索电视）",
                "📺 打开系统投屏设置（镜像）",
                "🔗 切换 LibreTV 服务器地址",
                "🔁 横屏 / 竖屏切换",
                "🔄 刷新页面",
                "🧹 清除缓存",
                "❓ 投屏使用说明"
        };
        new AlertDialog.Builder(this)
                .setTitle("投屏菜单")
                .setItems(items, (dialog, which) -> {
                    switch (which) {
                        case 0:
                            smartCast();
                            break;
                        case 1:
                            openSystemCastSettings();
                            break;
                        case 2:
                            promptServerUrl();
                            break;
                        case 3:
                            toggleOrientation();
                            break;
                        case 4:
                            web.reload();
                            break;
                        case 5:
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

    /** 智能投屏：抓取当前视频直链 → 局域网搜索 DLNA 电视 → 直连播放；搜不到再退回外部应用 */
    private void smartCast() {
        web.evaluateJavascript(JS_EXTRACT_VIDEO, new android.webkit.ValueCallback<String>() {
            @Override
            public void onReceiveValue(String value) {
                String u = value == null ? "" : value.replaceAll("^\"|\"$", "").trim();
                if (u.length() == 0 && lastMediaUrl != null) {
                    u = lastMediaUrl; // 兜底：用最近拦截到的视频直链
                }
                if (u.length() == 0) {
                    toast("未捕获到视频地址，请先开始播放视频");
                    return;
                }
                showDevicePicker(u);
            }
        });
    }

    // ==================== DLNA 直连投屏 ====================

    /** SSDP 搜索局域网内的 DLNA 电视（MediaRenderer），弹出选择列表 */
    private void showDevicePicker(final String videoUrl) {
        toast("正在搜索局域网电视…");
        final List<String[]> devices = new ArrayList<>();
        new Thread(new Runnable() {
            @Override
            public void run() {
                dlnaDiscover(devices, 3500);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        List<String> options = new ArrayList<>();
                        for (String[] d : devices) {
                            options.add("📺 " + d[0]);
                        }
                        if (activeCastControlUrl != null) {
                            options.add("⏹ 停止投屏（" + activeCastName + "）");
                        }
                        options.add("🔁 用其他应用播放（VLC / Web Video Caster）");
                        options.add("🔄 重新搜索");
                        options.add("❓ 搜不到电视？看提示");
                        final String[] arr = options.toArray(new String[0]);
                        new AlertDialog.Builder(MainActivity.this)
                                .setTitle("选择投屏设备（找到 " + devices.size() + " 台）")
                                .setItems(arr, (dialog, which) -> {
                                    String opt = arr[which];
                                    if (opt.startsWith("📺")) {
                                        String[] d = devices.get(which);
                                        activeCastName = d[0];
                                        activeCastControlUrl = d[1];
                                        dlnaPlay(d[1], videoUrl, d[0]);
                                    } else if (opt.startsWith("⏹")) {
                                        final String ctl = activeCastControlUrl;
                                        dlnaControlAsync(ctl, "Stop", "<InstanceID>0</InstanceID>");
                                        activeCastName = null;
                                        activeCastControlUrl = null;
                                        toast("已停止投屏");
                                    } else if (opt.startsWith("🔁")) {
                                        castVideo(videoUrl);
                                    } else if (opt.startsWith("🔄")) {
                                        showDevicePicker(videoUrl);
                                    } else if (opt.startsWith("❓")) {
                                        showHelp();
                                    }
                                })
                                .setNegativeButton("取消", null)
                                .show();
                    }
                });
            }
        }, "dlna-discover").start();
    }

    /** 把视频推给电视：SetAVTransportURI + Play（后台线程） */
    private void dlnaPlay(final String controlUrl, final String videoUrl, final String name) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                String body = "<InstanceID>0</InstanceID><CurrentURI>" + xmlEscape(videoUrl)
                        + "</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>";
                boolean ok = dlnaControl(controlUrl, "SetAVTransportURI", body);
                if (ok) {
                    ok = dlnaControl(controlUrl, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>");
                }
                final boolean done = ok;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        toast(done ? "🎬 已投屏到 " + name
                                : "投屏失败：电视拒绝了请求，请确认电视已开启「DLNA / 多屏互动 / 投屏」开关");
                    }
                });
            }
        }, "dlna-play").start();
    }

    private void dlnaControlAsync(final String controlUrl, final String action, final String argsXml) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                dlnaControl(controlUrl, action, argsXml);
            }
        }, "dlna-ctl").start();
    }

    /** SSDP 组播搜索 + 拉取设备描述 XML，结果放入 devices（[friendlyName, AVTransport controlURL]） */
    private void dlnaDiscover(List<String[]> devices, long timeoutMs) {
        WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
        if (wm != null) {
            multicastLock = wm.createMulticastLock("ltv-dlna");
            multicastLock.setReferenceCounted(false);
            multicastLock.acquire();
        }
        try {
            DatagramSocket socket = new DatagramSocket();
            socket.setSoTimeout(600);
            byte[] msearch = ("M-SEARCH * HTTP/1.1\r\n"
                    + "HOST: 239.255.255.250:1900\r\n"
                    + "MAN: \"ssdp:discover\"\r\n"
                    + "MX: 2\r\n"
                    + "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n").getBytes(StandardCharsets.UTF_8);
            InetAddress group = InetAddress.getByName("239.255.255.250");
            Set<String> seen = new HashSet<>();
            long deadline = System.currentTimeMillis() + timeoutMs;
            for (int i = 0; i < 3; i++) {
                socket.send(new DatagramPacket(msearch, msearch.length, group, 1900));
                try { Thread.sleep(120); } catch (InterruptedException ignored) { }
            }
            byte[] buf = new byte[2048];
            while (System.currentTimeMillis() < deadline) {
                DatagramPacket dp = new DatagramPacket(buf, buf.length);
                try {
                    socket.receive(dp);
                } catch (java.net.SocketTimeoutException e) {
                    continue;
                } catch (Exception e) {
                    break;
                }
                String resp = new String(dp.getData(), 0, dp.getLength(), StandardCharsets.UTF_8);
                String location = headerValue(resp, "LOCATION");
                if (location == null || !seen.add(location)) {
                    continue;
                }
                String[] dev = fetchRenderer(location);
                if (dev != null) {
                    devices.add(dev);
                }
            }
            socket.close();
        } catch (Exception e) {
            // WiFi 多播不可用 / 网络异常：留空设备列表
        } finally {
            if (multicastLock != null) {
                try { multicastLock.release(); } catch (Exception ignored) { }
            }
        }
    }

    /** 拉取设备描述 XML，返回 [friendlyName, AVTransport controlURL]；非渲染设备返回 null */
    private String[] fetchRenderer(String location) {
        try {
            String xml = httpGet(location, 3000);
            String name = firstTag(xml, "friendlyName");
            String controlUrl = null;
            Matcher m = Pattern.compile("<service>.*?</service>", Pattern.DOTALL).matcher(xml);
            while (m.find()) {
                String svc = m.group();
                if (svc.contains("AVTransport")) {
                    controlUrl = firstTag(svc, "controlURL");
                    break;
                }
            }
            if (name == null || controlUrl == null) {
                return null;
            }
            URL abs = new URL(new URL(location), controlUrl);
            return new String[]{xmlUnescape(name), abs.toString()};
        } catch (Exception e) {
            return null;
        }
    }

    /** 发送 AVTransport SOAP 控制命令，返回是否成功 */
    private static boolean dlnaControl(String controlUrl, String action, String argsXml) {
        try {
            String soap = "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                    + "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\""
                    + " s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">"
                    + "<s:Body><u:" + action + " xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\">"
                    + argsXml + "</u:" + action + "></s:Body></s:Envelope>";
            HttpURLConnection conn = (HttpURLConnection) new URL(controlUrl).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(4000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "text/xml; charset=\"utf-8\"");
            conn.setRequestProperty("SOAPACTION",
                    "\"urn:schemas-upnp-org:service:AVTransport:1#" + action + "\"");
            OutputStream os = conn.getOutputStream();
            os.write(soap.getBytes(StandardCharsets.UTF_8));
            os.close();
            int code = conn.getResponseCode();
            conn.disconnect();
            return code >= 200 && code < 300;
        } catch (Exception e) {
            return false;
        }
    }

    private static String httpGet(String url, int timeoutMs) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setConnectTimeout(timeoutMs);
        conn.setReadTimeout(timeoutMs);
        BufferedReader r = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) {
            sb.append(line).append('\n');
        }
        r.close();
        conn.disconnect();
        return sb.toString();
    }

    private static String headerValue(String resp, String key) {
        for (String line : resp.split("\r\n")) {
            int idx = line.indexOf(':');
            if (idx > 0 && line.substring(0, idx).trim().equalsIgnoreCase(key)) {
                return line.substring(idx + 1).trim();
            }
        }
        return null;
    }

    private static String firstTag(String xml, String tag) {
        Matcher m = Pattern.compile("<" + tag + "[^>]*>(.*?)</" + tag + ">", Pattern.DOTALL)
                .matcher(xml);
        return m.find() ? m.group(1).trim() : null;
    }

    private static String xmlUnescape(String s) {
        return s.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", "\"").replace("&apos;", "'").replace("&amp;", "&");
    }

    private static String xmlEscape(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    /** JS 桥：网页内「投屏」按钮回调到这里（点按=直连投屏，长按=菜单） */
    private class Bridge {
        @JavascriptInterface
        public void smartCast() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    MainActivity.this.smartCast();
                }
            });
        }

        @JavascriptInterface
        public void openMenu() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    showCastMenu();
                }
            });
        }
    }

    /** 通过 Android Intent 把视频直链交给外部投屏/播放应用（DLNA 搜不到时的退路） */
    private void castVideo(String url) {
        String mime = url.toLowerCase().contains(".m3u8") ? "application/x-mpegURL" : "video/*";
        Intent it = new Intent(Intent.ACTION_VIEW);
        it.setDataAndType(Uri.parse(url), mime);
        try {
            startActivity(Intent.createChooser(it, "选择投屏播放器（VLC / Web Video Caster 等）"));
        } catch (Exception e) {
            toast("未找到可用的投屏应用，请先安装 VLC 或 Web Video Caster");
        }
    }

    /** 判断是否是视频直链（m3u8 / mpd / flv / mp4） */
    private static boolean isMediaUrl(String url) {
        if (url == null) {
            return false;
        }
        String u = url.toLowerCase();
        return u.contains(".m3u8") || u.contains(".mpd") || u.contains(".flv")
                || u.contains(".mp4") || u.contains("/m3u8");
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
        // 退出全屏后恢复跟随系统自动旋转，并还原状态栏
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if (savedStatusBarColor != Integer.MIN_VALUE) {
            getWindow().setStatusBarColor(savedStatusBarColor);
            getWindow().setNavigationBarColor(savedNavBarColor);
            savedStatusBarColor = Integer.MIN_VALUE;
            savedNavBarColor = Integer.MIN_VALUE;
        }
    }

    /** 手动横竖屏切换（网页自身 CSS 全屏无法被系统感知时的兜底） */
    private void toggleOrientation() {
        int cur = getResources().getConfiguration().orientation;
        if (cur == android.content.res.Configuration.ORIENTATION_LANDSCAPE) {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
            toast("已切回竖屏（跟随系统）");
        } else {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
            toast("已切换横屏");
        }
    }

    private void enterImmersive() {
        // 强制全屏窗口 + 状态栏/导航栏染黑，压掉 HTML5 全屏时顶部露出的白条
        if (savedStatusBarColor == Integer.MIN_VALUE) {
            savedStatusBarColor = getWindow().getStatusBarColor();
            savedNavBarColor = getWindow().getNavigationBarColor();
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().setStatusBarColor(android.graphics.Color.BLACK);
        getWindow().setNavigationBarColor(android.graphics.Color.BLACK);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onBackPressed() {
        // 1) 系统 HTML5 全屏：先退出全屏
        if (customView != null) {
            exitCustomView();
            return;
        }
        // 2) 网页自身全屏（CSS/播放器全屏）：尝试让页面退出全屏，其次返回上一页
        web.evaluateJavascript(
                "(function(){try{if(document.fullscreenElement||document.webkitFullscreenElement)"
                        + "{(document.exitFullscreen||document.webkitExitFullscreen).call(document);return 'fs';}}catch(e){}"
                        + "try{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,which:27,bubbles:true}));}catch(e){}"
                        + "return 'no';})()",
                new android.webkit.ValueCallback<String>() {
                    @Override
                    public void onReceiveValue(String value) {
                        if (value != null && value.contains("fs")) {
                            return; // 页面已退出全屏，不再往下走
                        }
                        if (web.canGoBack()) {
                            web.goBack();
                            return;
                        }
                        new AlertDialog.Builder(MainActivity.this)
                                .setMessage("退出 LibreTV 投屏版？")
                                .setPositiveButton("退出", (dialog, which) -> finish())
                                .setNegativeButton("取消", null)
                                .show();
                    }
                });
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
    # 官方图标（PNG 二进制，覆盖全部密度；不再使用自适应矢量图标）
    import base64 as _b64
    for _rel, _b in OFFICIAL_ICONS_B64.items():
        _p = os.path.join("app", "src", "main", "res", *_rel.split("/"))
        os.makedirs(os.path.dirname(_p), exist_ok=True)
        with open(_p, "wb") as _f:
            _f.write(_b64.b64decode(_b))
        print("  生成", _p.replace(os.sep, "/"))

    # ---- 签名 ---------------------------------------------------------------
    ensure_keystore()

    print()
    print("[setup_project] 工程生成完毕 ✅")
    print("  下一步: gradle assembleRelease --no-daemon")
    print("  产物  : app/build/outputs/apk/release/app-release.apk")


if __name__ == "__main__":
    main()
