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
        versionCode 5
        versionName "1.3.0"
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
    <string name="help_text">直连投屏流程：\\n1. 手机和电视连同一个 WiFi；\\n2. 在本 App 播放视频，播放器控制条右侧会出现「投屏」按钮；\\n3. 点「投屏」→ 自动搜索局域网电视（海信 / 小米 / TCL / 当贝等 DLNA 设备）→ 选中电视即开始播放，无需任何第三方软件。\\n\\n说明：\\n· 长按「投屏」按钮可打开功能菜单（切换服务器 / 横竖屏 / 清缓存等）；\\n· 搜不到电视时，确认电视已开启「DLNA / 多屏互动 / 投屏」开关（各品牌叫法不同）；\\n· 也可以选「用其他应用播放」，交给 VLC / Web Video Caster；\\n· 投屏开始后可锁屏或退出本 App，电视独立播放。\\n\\n· 投屏时手机和电视请勿开热点隔离或访客网络。\\n\\n影片筛选：\\n· 非播放页右下角有「筛选」悬浮键 → 选电影/剧集 + 类型/地区/年份 → 点海报直接搜片源播放；\\n· 筛选使用本站豆瓣接口，若为空请先在本站登录。</string>
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

    /** 注入网页的「筛选」功能：参考老版 LibreTV 安卓 app 的豆瓣标签筛选。
     *  仅在非播放页显示筛选键；面板内分类别/标签/年份，点海报自动搜片源并跳播放页。 */
    private static final String JS_INJECT_FILTER =
            "(function(){"
            + "if(window.__ltvFilterInit){return;}"
            + "window.__ltvFilterInit=1;"
            + "var MOVIE=['热门','最新','经典','豆瓣高分','冷门佳片','华语','欧美','韩国','日本','动作','喜剧','爱情','科幻','悬疑','恐怖','治愈','动画'];"
            + "var TV=['热门','美剧','英剧','韩剧','日剧','国产剧','港剧','日本动画','综艺','纪录片'];"
            + "var YEARS=['热门','2026','2025','2024','2023','2022','2021','2020'];"
            + "var curType='movie',curTag='热门';"
            + "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');}"
            + "setInterval(function(){"
            + "var f=document.getElementById('__ltv_filter');"
            + "if(document.querySelector('video')){if(f&&f.parentNode){f.parentNode.removeChild(f);}return;}"
            + "if(!document.body||f){return;}"
            + "f=document.createElement('button');f.id='__ltv_filter';f.textContent='筛选';"
            + "f.style.cssText='position:fixed;right:14px;bottom:24px;z-index:99998;padding:6px 14px;border-radius:16px;border:1px solid rgba(255,255,255,.35);background:rgba(18,18,26,.75);color:#fff;font-size:13px;cursor:pointer;';"
            + "f.addEventListener('click',function(e){e.stopPropagation();openPanel();});"
            + "document.body.appendChild(f);"
            + "},900);"
            + "function openPanel(){"
            + "if(document.getElementById('__ltv_ovl')){return;}"
            + "var ovl=document.createElement('div');ovl.id='__ltv_ovl';"
            + "ovl.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.8);overflow-y:auto;padding:14px;';"
            + "var panel=document.createElement('div');"
            + "panel.style.cssText='max-width:860px;margin:0 auto;background:#141420;border:1px solid #2a2a3a;border-radius:12px;padding:14px;';"
            + "ovl.appendChild(panel);document.body.appendChild(ovl);"
            + "ovl.addEventListener('click',function(e){if(e.target===ovl){ovl.remove();}});"
            + "render(panel);"
            + "}"
            + "function chipRow(label,arr,active,onClick){"
            + "var row=document.createElement('div');"
            + "row.style.cssText='margin:6px 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center;';"
            + "var lab=document.createElement('span');lab.textContent=label;"
            + "lab.style.cssText='color:#8a8aa0;font-size:12px;min-width:34px;';row.appendChild(lab);"
            + "arr.forEach(function(t){"
            + "var b=document.createElement('button');b.textContent=t;var on=(t===active);"
            + "b.style.cssText='padding:4px 10px;border-radius:12px;font-size:12px;cursor:pointer;border:1px solid '+(on?'#e91e63':'#333')+';background:'+(on?'#e91e63':'#1e1e2c')+';color:'+(on?'#fff':'#bbb')+';';"
            + "b.addEventListener('click',function(){onClick(t);});row.appendChild(b);"
            + "});return row;"
            + "}"
            + "function render(panel){"
            + "panel.innerHTML='';"
            + "var head=document.createElement('div');"
            + "head.style.cssText='display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;';"
            + "head.innerHTML='<span style=\"color:#fff;font-size:16px;font-weight:600\">\uD83C\uDFAC 筛选 · 豆瓣精选</span>';"
            + "var close=document.createElement('button');close.textContent='\\u2715';"
            + "close.style.cssText='background:none;border:none;color:#999;font-size:18px;cursor:pointer;';"
            + "close.addEventListener('click',function(){var o=document.getElementById('__ltv_ovl');if(o){o.remove();}});"
            + "head.appendChild(close);panel.appendChild(head);"
            + "var tabs=document.createElement('div');tabs.style.cssText='display:flex;gap:8px;margin-bottom:4px;';"
            + "[['movie','电影'],['tv','剧集']].forEach(function(pr){"
            + "var b=document.createElement('button');b.textContent=pr[1];var on=curType===pr[0];"
            + "b.style.cssText='flex:1;padding:8px;border-radius:8px;font-size:14px;cursor:pointer;border:none;background:'+(on?'#e91e63':'#1e1e2c')+';color:'+(on?'#fff':'#bbb')+';';"
            + "b.addEventListener('click',function(){curType=pr[0];curTag='热门';render(panel);});"
            + "tabs.appendChild(b);"
            + "});"
            + "panel.appendChild(tabs);"
            + "var tags=curType==='movie'?MOVIE:TV;"
            + "panel.appendChild(chipRow('类型',tags,tags.indexOf(curTag)>=0?curTag:'热门',function(t){curTag=t;render(panel);}));"
            + "panel.appendChild(chipRow('年份',YEARS,YEARS.indexOf(curTag)>=0?curTag:null,function(t){curTag=t;render(panel);}));"
            + "var grid=document.createElement('div');"
            + "grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:10px;margin-top:10px;';"
            + "panel.appendChild(grid);loadGrid(grid);"
            + "}"
            + "function loadGrid(grid){"
            + "grid.innerHTML='<div style=\"color:#8a8aa0;padding:26px;grid-column:1/-1;text-align:center\">加载中…</div>';"
            + "var url='/api/douban?type='+encodeURIComponent(curType)+'&tag='+encodeURIComponent(curTag)+'&pageStart=0&pageSize=24';"
            + "fetch(url,{credentials:'include'}).then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.list||d.subjects||d.items||d.data))||[];"
            + "if(!Array.isArray(list)||!list.length){"
            + "grid.innerHTML='<div style=\"color:#8a8aa0;padding:26px;grid-column:1/-1;text-align:center\">暂无内容（若一直为空，请先在本站登录）</div>';return;}"
            + "grid.innerHTML='';"
            + "list.forEach(function(it){"
            + "var t=it.title||it.name||'';"
            + "var img=it.poster||it.cover||it.img||'';"
            + "if(img){img=img.replace(/img\\d+\\.doubanio\\.com/g,'img.doubanio.cmliussss.net');}"
            + "var rate=it.rate||it.rating||'';"
            + "var card=document.createElement('div');card.style.cssText='cursor:pointer;';"
            + "card.innerHTML='<div style=\"position:relative\"><img src=\"'+esc(img)+'\" loading=\"lazy\" style=\"width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:8px;background:#222\">'"
            + "+(rate?'<span style=\"position:absolute;right:4px;top:4px;background:rgba(0,0,0,.7);color:#f5c518;font-size:11px;padding:1px 4px;border-radius:4px\">\\u2605'+esc(rate)+'</span>':'')+'</div>'"
            + "+'<div style=\"color:#ddd;font-size:12px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\">'+esc(t)+'</div>';"
            + "card.addEventListener('click',function(){playTitle(t);});"
            + "grid.appendChild(card);"
            + "});"
            + "}).catch(function(e){"
            + "grid.innerHTML='<div style=\"color:#f88;padding:26px;grid-column:1/-1;text-align:center\">加载失败：'+esc(e.message||e)+'</div>';});"
            + "}"
            + "function playTitle(title){"
            + "if(!title){return;}"
            + "fetch('/api/search',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:title})})"
            + ".then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.regular_results||d.results||d.list||d.data))||[];"
            + "if(!Array.isArray(list)){list=[];}"
            + "var hit=null;"
            + "for(var i=0;i<list.length;i++){"
            + "var it=list[i];var src=it.source||it.sourceKey||'';var id=it.vod_id||it.id||'';"
            + "if(src&&id){hit=it;break;}"
            + "}"
            + "if(!hit){alert('未找到可播放的片源：'+title);return;}"
            + "var src=hit.source||hit.sourceKey||'';var id=hit.vod_id||hit.id||'';"
            + "var t=hit.vod_name||hit.title||title;"
            + "var ov=document.getElementById('__ltv_ovl');if(ov){ov.remove();}"
            + "location.href='/watch?source='+encodeURIComponent(src)+'&id='+encodeURIComponent(id)+'&title='+encodeURIComponent(t);"
            + "}).catch(function(e){alert('搜索失败：'+(e.message||e));});"
            + "}"
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
