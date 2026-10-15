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
        versionCode 10
        versionName "1.6.0"
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
    <string name="app_name">LibreTV</string>
    <string name="default_server_url">__DEFAULT_URL__</string>
    <string name="help_text">直连投屏流程：\\n1. 手机和电视连同一个 WiFi；\\n2. 在本 App 播放视频，播放器控制条右侧会出现「投屏」按钮；\\n3. 点「投屏」→ 自动搜索局域网电视（海信 / 小米 / TCL / 当贝等 DLNA 设备）→ 选中电视即开始播放，无需任何第三方软件。\\n\\n说明：\\n· 长按「投屏」按钮可打开功能菜单（切换服务器 / 横竖屏 / 清缓存等）；\\n· 搜不到电视时，确认电视已开启「DLNA / 多屏互动 / 投屏」开关（各品牌叫法不同）；\\n· 也可以选「用其他应用播放」，交给 VLC / Web Video Caster；\\n· 投屏开始后可锁屏或退出本 App，电视独立播放。\\n\\n· 投屏时手机和电视请勿开热点隔离或访客网络。\\n\\n影片筛选：\\n· 非播放页右下角有「筛选」悬浮键 → 全屏浏览页：电影/剧集切换、类型/地区/年份筛选行、海报墙上滑自动加载；\\n· 顶部搜索框可直搜片名；点海报自动找片源播放；\\n· 点右上「设为启动页」后，每次打开 App 直接进入筛选页；\\n· 筛选使用本站豆瓣接口，若为空请先在本站登录。\\n\\n主页推荐：\\n· 首次使用会自动把主页推荐从「豆瓣」切换为「影视榜单」（电影周榜/剧集榜/综艺榜），与筛选页内容互补。</string>
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
# 官方 LibreTV 图标（黑底青粉渐变 L，取自官方发行 APK res/as.png 432x432 缩放）
OFFICIAL_ICONS_B64 = {
    "mipmap-mdpi/ic_launcher.png":
        "iVBORw0KGgoAAAANSUhEUgAAACQAAAAkCAYAAADhAJiYAAAACXBIWXMAAA7EAAAOxAGVKw4bAAABy0lEQVR4nGNgGAWjYBSMglFA"
        "BfDkiTDDyyf6DG8fajP8/8800M5hYL53O4Xx1fMPTM+f3WK4epVnoN3DwH7hRgbrzQe/OK7fezIoHCSx/3SG+PHrv6SPXn0iun8Q"
        "OEhrw7EMnW3nfulvPfdEe9X+gXeQw6L9GY7Lj/9yXnrsicNgcJDf1F0ZgbMP/gqaceBJ6NRB4KDYzg0ZCb07fyV27xgcDsqsWpmR"
        "W7fhV27N+idZDasG3kEVRUsTykuW/SwtWvokK2sQOKgpZ2FMY+b8n/UZ8540ZE0deAf1psyI6Uqa8bMjacbgcNDMuInx0+Im/gTi"
        "J1NDB4GDFoc3pq+M6vq5PKrz6qLYEu7Nvg1cG/zKpDZE1MPxqtAGCSBmo4uDNgdXZewJa3y6I6wxdUtUheC+8PrGfeENh/dFNBwF"
        "4YNAfCCiYfn+0HoVujjooE9J1ImA6rTdoeX8p4Iqm08HV309E1z9/1xQ9f8LQHwxqApIV+06FlooRBcHHXUrEbsKjI6jgRli5/1K"
        "8y/5ldZc8SmtuQbEN4D4tm9Z9W3vIr//DAyMdHEQDIAs/B8ayowVNzQMfMONSEDfUCMAGAsLCzkH2hGjYBSMgkEFAN+E1sUWONY5"
        "AAAAAElFTkSuQmCC"
        ,
    "mipmap-mdpi/ic_launcher_round.png":
        "iVBORw0KGgoAAAANSUhEUgAAACQAAAAkCAYAAADhAJiYAAAACXBIWXMAAA7EAAAOxAGVKw4bAAABy0lEQVR4nGNgGAWjYBSMglFA"
        "BfDkiTDDyyf6DG8fajP8/8800M5hYL53O4Xx1fMPTM+f3WK4epVnoN3DwH7hRgbrzQe/OK7fezIoHCSx/3SG+PHrv6SPXn0iun8Q"
        "OEhrw7EMnW3nfulvPfdEe9X+gXeQw6L9GY7Lj/9yXnrsicNgcJDf1F0ZgbMP/gqaceBJ6NRB4KDYzg0ZCb07fyV27xgcDsqsWpmR"
        "W7fhV27N+idZDasG3kEVRUsTykuW/SwtWvokK2sQOKgpZ2FMY+b8n/UZ8540ZE0deAf1psyI6Uqa8bMjacbgcNDMuInx0+Im/gTi"
        "J1NDB4GDFoc3pq+M6vq5PKrz6qLYEu7Nvg1cG/zKpDZE1MPxqtAGCSBmo4uDNgdXZewJa3y6I6wxdUtUheC+8PrGfeENh/dFNBwF"
        "4YNAfCCiYfn+0HoVujjooE9J1ImA6rTdoeX8p4Iqm08HV309E1z9/1xQ9f8LQHwxqApIV+06FlooRBcHHXUrEbsKjI6jgRli5/1K"
        "8y/5ldZc8SmtuQbEN4D4tm9Z9W3vIr//DAyMdHEQDIAs/B8ayowVNzQMfMONSEDfUCMAGAsLCzkH2hGjYBSMgkEFAN+E1sUWONY5"
        "AAAAAElFTkSuQmCC"
        ,
    "mipmap-hdpi/ic_launcher.png":
        "iVBORw0KGgoAAAANSUhEUgAAADYAAAA2CAYAAACMRWrdAAAACXBIWXMAAA7EAAAOxAGVKw4bAAADA0lEQVR4nO2YW0gUURiA11WR"
        "npJC6CGsKOwtDd/EwiBCzcuKjqumsmWYFuaGrvfVo7ZpKq4TKV7ILZcWM2m1TcVaXC+Jrpf1Vnq0vIWFgvjk5kPR3xmRCLJefNg8"
        "nA8+5szAwP8xwxwYkYjBYDAYDAaDwWAw/gTAzmkBn3ZYX7u47dqSF7nmYOux9g7H2TssfywRb6xtitdXN8WrKxbRxsZBW4+1d4Qw"
        "jHnxyhew//QZHBeWsWhx0dnWY+0dEuZkmeId8RI4TS/Bgcl57ExL2OEeC39oZA5chmbhyMA0Pj5GSdiJjkH+ZPc7OGWaAjfjOPYw"
        "jdERdqa5j3dvG4Ozryzg2TqMPfSUhHlru/nzTUPg02SGC7oB7ENDGEfCLtUZeb+Gfrj8pB8C6vuwRGOiIyzkYScfWtMDXDWxqoue"
        "sKj7Bj6aN0Ks+g3ElnVimZqSsOuomU8oaodEVRskFhiwHOnpCLuV8ZSXK/Ugz3kByVnNdIQhhMQKha5IkfYMFIpGSE1txHI5BWEC"
        "SK5FyttayEnSQnZSA0ZyDR1hqpsaVJhQDwXE/BuP6Akrja9DxddroDiuFlRx1VgtoySMv1aJKq5WglpWBeWyShKm3v9hIBLZ1cSW"
        "q2pjKqA2hofq6AqsoSFM+Nw/lt5V666Ugi6qDLSRJTPUhDWH5fGGiHtgkKq+tUpVVe1+D5yQCIn1nNLzZXheeAuXKzXsYktEtlcT"
        "ud/WDbsihHWEZPA9HPpuCs173s5lugivpzFCea4rAs2aIvO3uok9xN4d+7aPaMsUmVsIZB+0dcOuCGG9QanqoZDs128D012FKLNU"
        "6T7AZU0OhuX8MIflwDBxhDhKtPwy+6s5NFNi6/n/ivDK9fnfiRqXZLoJ5xb/lGOjkjTjWEjG5rgk3ToRnGadCk63vifH6aA06wwR"
        "E+eC0z9M+CUdtfX8/2TEM95ReFLb68BkV0tgit9kgMJ/esfZ35wX9CVr3xRv8EEU/H9kMPYnwtdWJpPt/41+F+y4/3XzZjAYDAaD"
        "wRD9BM9DmVkfHPuwAAAAAElFTkSuQmCC"
        ,
    "mipmap-hdpi/ic_launcher_round.png":
        "iVBORw0KGgoAAAANSUhEUgAAADYAAAA2CAYAAACMRWrdAAAACXBIWXMAAA7EAAAOxAGVKw4bAAADA0lEQVR4nO2YW0gUURiA11WR"
        "npJC6CGsKOwtDd/EwiBCzcuKjqumsmWYFuaGrvfVo7ZpKq4TKV7ILZcWM2m1TcVaXC+Jrpf1Vnq0vIWFgvjk5kPR3xmRCLJefNg8"
        "nA8+5szAwP8xwxwYkYjBYDAYDAaDwWAw/gTAzmkBn3ZYX7u47dqSF7nmYOux9g7H2TssfywRb6xtitdXN8WrKxbRxsZBW4+1d4Qw"
        "jHnxyhew//QZHBeWsWhx0dnWY+0dEuZkmeId8RI4TS/Bgcl57ExL2OEeC39oZA5chmbhyMA0Pj5GSdiJjkH+ZPc7OGWaAjfjOPYw"
        "jdERdqa5j3dvG4Ozryzg2TqMPfSUhHlru/nzTUPg02SGC7oB7ENDGEfCLtUZeb+Gfrj8pB8C6vuwRGOiIyzkYScfWtMDXDWxqoue"
        "sKj7Bj6aN0Ks+g3ElnVimZqSsOuomU8oaodEVRskFhiwHOnpCLuV8ZSXK/Ugz3kByVnNdIQhhMQKha5IkfYMFIpGSE1txHI5BWEC"
        "SK5FyttayEnSQnZSA0ZyDR1hqpsaVJhQDwXE/BuP6Akrja9DxddroDiuFlRx1VgtoySMv1aJKq5WglpWBeWyShKm3v9hIBLZ1cSW"
        "q2pjKqA2hofq6AqsoSFM+Nw/lt5V666Ugi6qDLSRJTPUhDWH5fGGiHtgkKq+tUpVVe1+D5yQCIn1nNLzZXheeAuXKzXsYktEtlcT"
        "ud/WDbsihHWEZPA9HPpuCs173s5lugivpzFCea4rAs2aIvO3uok9xN4d+7aPaMsUmVsIZB+0dcOuCGG9QanqoZDs128D012FKLNU"
        "6T7AZU0OhuX8MIflwDBxhDhKtPwy+6s5NFNi6/n/ivDK9fnfiRqXZLoJ5xb/lGOjkjTjWEjG5rgk3ToRnGadCk63vifH6aA06wwR"
        "E+eC0z9M+CUdtfX8/2TEM95ReFLb68BkV0tgit9kgMJ/esfZ35wX9CVr3xRv8EEU/H9kMPYnwtdWJpPt/41+F+y4/3XzZjAYDAaD"
        "wRD9BM9DmVkfHPuwAAAAAElFTkSuQmCC"
        ,
    "mipmap-xhdpi/ic_launcher.png":
        "iVBORw0KGgoAAAANSUhEUgAAAEgAAABICAYAAABV7bNHAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAEmklEQVR4nO3aa0xbZRzHcQqM"
        "MchQp2aZTqMJESPJMt0LYoZKdGGb415KW0p34bZNQAq05W4P4AIZEEGGXAdLByLlMoVRDgpyKaHjTic9GzDBgXKJRnwlvuLv8/Ri"
        "iImvJOs0/0/yy3PSw4tzvgmkL7CzQwghhBBCCCGEEEIIIfSfwzCOjqsPvR1+WeU7bJKR03Fj2deuv9/R1o/2eEhIcHPYWO7g/bax"
        "Zb+5vmX/6/oWb+OnaTuDwdXWj/Z4oIFWfmB56+tgv7YG9qtr4PhwmcNAViSQ4/wD1n7pR3BYXIE9D1bAaW4RA1kdkEjcnKfvs073"
        "lmAvtwQus4vgOj3PHcRAZjTQAf0s+8TkAjw1MQ/PjM/Bs3ojd7AHA5nQQC/0T7OHhzl4UcfBS0NGeLnvLgayooE8usdZj14DvPq1"
        "ATzJXtNOckcwkJk7CXS0Xc8evT0Fb3RMwjG69nHuiLoHA1E00FvNw6x3yxi83TIK72jImvScLwYycz8tcXtXPcSe+FwPJxr1cPKm"
        "Hnxv6DCQFQ3kV9PH+tXrIKBOB0HXyaoHON9CDGTiRQLxy79hQysHQVAxAEIywbU+ToqBzGig8BKWlXzaBxGlvSAtISvuwUBWNFBk"
        "QRcbVchC9FUWYgrIrnRxUrkaA1E00AeqdjYutxPiczohgemA+OxbGMiKBkrM0LCyrHaQZbaBLIMsrZWTYyAzH5/zznJFU4c8tRlS"
        "lF+AXNkMyfImDLQDLzu5SZOR1ADpMrpGUCbexEA78D6OV2uYuBugsizrch0nl2IgK17+5XpN3sXrkHupDnIv1oEqppYEKsRAFryi"
        "S7WagugqyI+uhvyoargSVYGBduCVxFRpiiIroCiyEoouVMLVC+VcIQb6C++zyHJN2bkyMO1sGZScLcVAVgJPT6facyW3aiJKoEZK"
        "FlEKVRGfYCCrAI/j+9XhBdoGSRE0hBdBY3gxqMWFnBoDmUm8vNxahHlsu7gATBMWbLeK8r/VCJL2WX9mIrZqT/15xtm6/n8YvacR"
        "CBxs+T67jgbqCvuIZYV50BOWt90typv9Kiz3OLnFo/fbQmSHtCKmuFOk0t4W5mi1QpVWKzKvm1x3iywj16xI9WUrP+11G7/S7pK4"
        "e7n18jPZIYEKBkOzV3uDs04xDGNP7/VI5a79IlXFgIj5fUCcA4OiHBgSMzBETzKd2Lxhy3ThOT+3hWQcsvU77SoaaCQolR0Lzlwd"
        "4WeKGR8f0z8tDAco9w/z0/NHQrP+0IdmwR2yUcvG+WTknCCbtE5APgvL7qK/arZ+p13l/9wxl+ngtKaZoMxY7emEvfQzo4Bx0oco"
        "Uib4GZsT/HSYDEmHKbKZ4HQwkH0XZN6saWlgJCcXlLY9E5iaphFo/l9/gwSH39zXfyrRe8ESh+CN+H343lSg4s5MoNJoCFQY7wYo"
        "jLNkRn+l8R7dGYXxPtk82cIZORk5/eSjc/4p3jZ9mUeEBEp6fsw/yXPGP9U0I7k2nkzdsSTPBXIumE7zvn8/+ZUJ/1gXWz88Qgih"
        "f4l+EY2Li3vazvJtHf0NDSSTyZ609XMghBBCCCGEEELoUfoTwJOaM329aWkAAAAASUVORK5CYII="
        ,
    "mipmap-xhdpi/ic_launcher_round.png":
        "iVBORw0KGgoAAAANSUhEUgAAAEgAAABICAYAAABV7bNHAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAEmklEQVR4nO3aa0xbZRzHcQqM"
        "MchQp2aZTqMJESPJMt0LYoZKdGGb415KW0p34bZNQAq05W4P4AIZEEGGXAdLByLlMoVRDgpyKaHjTic9GzDBgXKJRnwlvuLv8/Ri"
        "iImvJOs0/0/yy3PSw4tzvgmkL7CzQwghhBBCCCGEEEIIIfSfwzCOjqsPvR1+WeU7bJKR03Fj2deuv9/R1o/2eEhIcHPYWO7g/bax"
        "Zb+5vmX/6/oWb+OnaTuDwdXWj/Z4oIFWfmB56+tgv7YG9qtr4PhwmcNAViSQ4/wD1n7pR3BYXIE9D1bAaW4RA1kdkEjcnKfvs073"
        "lmAvtwQus4vgOj3PHcRAZjTQAf0s+8TkAjw1MQ/PjM/Bs3ojd7AHA5nQQC/0T7OHhzl4UcfBS0NGeLnvLgayooE8usdZj14DvPq1"
        "ATzJXtNOckcwkJk7CXS0Xc8evT0Fb3RMwjG69nHuiLoHA1E00FvNw6x3yxi83TIK72jImvScLwYycz8tcXtXPcSe+FwPJxr1cPKm"
        "Hnxv6DCQFQ3kV9PH+tXrIKBOB0HXyaoHON9CDGTiRQLxy79hQysHQVAxAEIywbU+ToqBzGig8BKWlXzaBxGlvSAtISvuwUBWNFBk"
        "QRcbVchC9FUWYgrIrnRxUrkaA1E00AeqdjYutxPiczohgemA+OxbGMiKBkrM0LCyrHaQZbaBLIMsrZWTYyAzH5/zznJFU4c8tRlS"
        "lF+AXNkMyfImDLQDLzu5SZOR1ADpMrpGUCbexEA78D6OV2uYuBugsizrch0nl2IgK17+5XpN3sXrkHupDnIv1oEqppYEKsRAFryi"
        "S7WagugqyI+uhvyoargSVYGBduCVxFRpiiIroCiyEoouVMLVC+VcIQb6C++zyHJN2bkyMO1sGZScLcVAVgJPT6facyW3aiJKoEZK"
        "FlEKVRGfYCCrAI/j+9XhBdoGSRE0hBdBY3gxqMWFnBoDmUm8vNxahHlsu7gATBMWbLeK8r/VCJL2WX9mIrZqT/15xtm6/n8YvacR"
        "CBxs+T67jgbqCvuIZYV50BOWt90typv9Kiz3OLnFo/fbQmSHtCKmuFOk0t4W5mi1QpVWKzKvm1x3iywj16xI9WUrP+11G7/S7pK4"
        "e7n18jPZIYEKBkOzV3uDs04xDGNP7/VI5a79IlXFgIj5fUCcA4OiHBgSMzBETzKd2Lxhy3ThOT+3hWQcsvU77SoaaCQolR0Lzlwd"
        "4WeKGR8f0z8tDAco9w/z0/NHQrP+0IdmwR2yUcvG+WTknCCbtE5APgvL7qK/arZ+p13l/9wxl+ngtKaZoMxY7emEvfQzo4Bx0oco"
        "Uib4GZsT/HSYDEmHKbKZ4HQwkH0XZN6saWlgJCcXlLY9E5iaphFo/l9/gwSH39zXfyrRe8ESh+CN+H343lSg4s5MoNJoCFQY7wYo"
        "jLNkRn+l8R7dGYXxPtk82cIZORk5/eSjc/4p3jZ9mUeEBEp6fsw/yXPGP9U0I7k2nkzdsSTPBXIumE7zvn8/+ZUJ/1gXWz88Qgih"
        "f4l+EY2Li3vazvJtHf0NDSSTyZ609XMghBBCCCGEEELoUfoTwJOaM329aWkAAAAASUVORK5CYII="
        ,
    "mipmap-xxhdpi/ic_launcher.png":
        "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"
        "mEBn7ZvfSgAAAABJRU5ErkJggg=="
        ,
    "mipmap-xxhdpi/ic_launcher_round.png":
        "iVBORw0KGgoAAAANSUhEUgAAAGwAAABsCAYAAACPZlfNAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAHrklEQVR4nO3cf1DT9x3HcX5W"
        "XG3dD69s7W51667WrVu3Ms7vja6LHbVF5VdCfpCAIsM4f1B+h0BKAhLQYEEaEMWI6LCCVCxQBg7l95ffhN8REMSfiMbV+fVud7ur"
        "23ufbxJmZLv96HmXb+37cfe8z/ebbzyTe+nxh3c6OSGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCKHH52sFBc+7mOfec/ls"
        "PvHRbiS6zl2ROplMTzn6MyI77kePrnFlzHed75sfuDC3rd0j/fnWA9db19ud7kw+4+jPiOy4GwyUy515xvmz2+DC9qdb4HKHnLfn"
        "wXXuGo2DccxSMpjrrZuM8/w8ON+cB5ebN8lQpOtz4HblKu00iYNxytKiIsrt+g3G5eocsLleuQFul2+A+6Xr4D41i4NxzVJ9EeU+"
        "c41xnbkGbtPXwP3iVXhq6iosmbgCHuMzOBjXPJurpzwuXGKWmC6DB2np+Cw8PTYLy0ZmYNngFL0CB+OWb+r01PLhi8wzQzPwLGn5"
        "4DR8wzgN3xqYghU9JnoFjYNxiqc2l/LsnWCe650Ez55J+Dbp+e5J+G7nBXihfYxehYNxywtksJUdJubFDhOsbDfB90k/aDPBSy1j"
        "8NK5YRyMa1ZqdNSqplHm5aZRYFt1fhReIf2ocQReaRikV9XQOBiX/FClo149O8S8enYY2H7SMASv1Q/Bz/4wCK/V9uNgXLOaDOZV"
        "a2Re/9QI5IRf1BjBm7SmegC8q3poHxyMW36q0FJvnOlnfKr64Q3Sr073w5un++DXlX3wZkU3DsY1ryt01NrKHoZX0QtrK3rgLdJv"
        "ynvA92Q3+JZ10T4lOBinrInXUu+c7GLWfdQNb5/ognUkv7IuWH+8E94t7aADcDBuWROtpfyP0cyGYzRsJPmX0hB4lIagkg4IMLTj"
        "YFzjQwbjH2lngg3twCY43A4hbMVtIChqwcG4hrddS4kOtTKig63AJi5qBQk5JQdaQKxvwsG4xne7hpIVNjOhhc0gLWgGWUEThOmb"
        "IDy/CWR5jXSkrgYH4xK/KA21Je8cs3l/I0Sw5TXCltxGiNxH0jXgYFzjF6Gh5LqzzNacBmCT722AbWzZpMw6HIxr/GUqape2jtmZ"
        "VQc7taTMOti1uw6iMz6FneoaOlKBg3EKnwwWq6lhYjQ1EKOuhpg0a7HvfwLRqVW0AgfjFr5IQcWrzjBxqjMQp6qCuNQqiCXFpZyG"
        "GEUlDsY1Aony50nKj+8lKCvBUrItRSXEJVbgYFwjlxd/J1VxyqxILId/lmAtMe4EGawEB+OS1CiDpzr+pFkVewIsxVhLJSljjuNg"
        "XJMale+5O6bMrIk+Dppd1tSkNNL7O0tpRSQOxinsYNm7jpt3by+FDLvSSerfHcHBuIYdbO/2UnPWthLQ2pUpL4GMrQZah4NxSxYZ"
        "bN+2I+Y9Ww2QvVCUAbJImVHFOBjXZIXme+bKD5tzoopB99uH7SVlRx7EwbiGHUwfdcicF3kQ8rbYIte55MzZXIiDcU1WaJbngcgi"
        "sz6iEBb60FbepgIcjGvyyWCGLYXmg5v0YF9RuB4Kw/LpkkgdDsYlCt8dq0s37b9bEp4PJWEPO0IyyPbjYFyTsHaz10dhH9wrC8uF"
        "MhlJyp55lutjkg/okgAcjFMUPBn1sUzHnJLlwCnpPhI5Q3MsZ7k0h67Bv2HcoiKD1UizmerQPWDfJ+I9D6pE2sP10foli38Nj8dz"
        "k3t5uX/RhE5CV0d81yeChiei/hiayTRItNAgJkkySdq/1Yu1LZXC5O8tfn8VX/VirSR9X7U4rdiaurhaaK1WbMtyn2Y5F+5ryX2d"
        "9fmh8hDlOkd81yeCxkdENYvSmWZxBjSLMqBJmPH38wJ133mx5uXF7z0TnPhck0hTcV6a+aBJlgnN0kdrIa+1SG2R61ZSm+20XIex"
        "ae/Xh2recsR3fSJoffhUR4iaoYUaoIVqoPnqsQZ/pTd55Gz/vnO+ycvbJOpjrWLN522SdGgndYhJEmu0XZ12dS0Uao2WamZrAmI8"
        "HfR1v/x0ZLBevorpDVZBvyDtcmtw6tuwaKxK3o5lbcEpH3aK0v7aKVJDF6lbmAY9tnpt9dnVL0qDAaG1fpKR3BvFavJ+VXm9X/S/"
        "/FxE/yN2sCGBihkMSrndsz45MN0p3cX+eQsvwqNLkKzsFar+0huiAra+EHZcFQyQjGx8FQyxCR42TO5HFhJYGxaoPu8VpMY5LfoD"
        "gf4PByjx6vEg1exgcOqmYi+5u/2zAXLfHZiwY4Cfct8oSIFBfgoZh5zBKTAcrIQRtqAUGCWNkcaDlGBiC1TCBVsTbOS1SfJ8MlB5"
        "t/XdHd6O+q5PhL3e/j82BijkJmH6I/9rW6VQ6Nq//r3w4SDFnaGgZBgJVFgaDUyC0YAkGCeZ/JPggr8CJkiTlpJgamMSXLRremMi"
        "zJDzEnlOrgeGgmK/7qjv+kRgh2nhpbstfv3368KfNgYmbhvYkJAx7J9kaZRcLzS2ISnDZGtiIb8ES1OLeychY5qcY37x4n/3e6HH"
        "y/kxhhBCCCGEEPrKcxYKhcu8vLzc//tbkcNFRER4xMfH/1Iul+NgXxLO7L92O/pDIIQQQgghhBBCCCGEEEIIIYQQQgghhP6DfwA0"
        "mEBn7ZvfSgAAAABJRU5ErkJggg=="
        ,
    "mipmap-xxxhdpi/ic_launcher.png":
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
import java.net.URLEncoder;
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

    /** 注入网页的「筛选」首页：OK猫影视风格全屏浏览页（类别 + 类型/地区/年份 + 海报墙 + 滚动加载 + 站内搜索 + 可设启动页）。
     *  v1.5.0：fetch 全部带 8s 超时防 loading 卡死；切换时 abort 旧请求；标签扩充；主页推荐源自动切到影视榜单。 */
    private static final String JS_INJECT_FILTER =
            "(function(){"
            + "if(window.__ltvFilterInit){return;}"
            + "window.__ltvFilterInit=1;"
            + "var CONF={"
            + "movie:{'类型':['热门','最新','经典','豆瓣高分','冷门佳片','动作','喜剧','爱情','科幻','悬疑','恐怖','治愈','动画','纪录片','奇幻','冒险','战争','音乐','传记','历史','运动'],"
            + "'地区':['华语','欧美','韩国','日本'],"
            + "'年份':['2026','2025','2024','2023','2022','2021','2020','2019','2018']},"
            + "tv:{'类型':['热门','最新','经典','豆瓣高分','综艺','纪录片','日本动画','都市','悬疑','武侠','喜剧','爱情','古装','奇幻'],"
            + "'地区':['美剧','英剧','韩剧','日剧','国产剧','港剧','泰剧'],"
            + "'年份':['2026','2025','2024','2023','2022','2021','2020','2019','2018']}"
            + "};"
            + "var curType='movie',curSel={},pageStart=0,loading=false,hasMore=true,mode='filter',loadCtl=null,cache={},retried=false,curTotal=0,rexSeq=0,pendAppend=false,pendCk='';"
            + "function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');}"
            + "function videoOn(){return !!document.querySelector('video');}"
            + "function xfetch(url,opt){"
            + "var c=new AbortController();var t=setTimeout(function(){try{c.abort();}catch(e){}},8000);"
            + "var o=opt||{};o.signal=c.signal;"
            + "return fetch(url,o).then(function(r){clearTimeout(t);return r;},function(e){clearTimeout(t);throw e;});"
            + "}"
            + "function abortLoad(){if(loadCtl){try{loadCtl.abort();}catch(e){}}loadCtl=null;}"
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
            + "b.addEventListener('click',function(){if(curType!==pr[0]){curType=pr[0];curSel={};mode='filter';buildFilters(head);resetLoad();}});"
            + "tabs.appendChild(b);"
            + "});"
            + "head.appendChild(tabs);"
            + "var sr=document.createElement('div');sr.style.cssText='display:flex;gap:8px;margin-top:10px;';"
            + "var inp=document.createElement('input');inp.placeholder='搜索片名…';"
            + "inp.style.cssText='flex:1;padding:8px 12px;border-radius:8px;border:1px solid #2a2a3a;background:#1e1e2c;color:#fff;font-size:13px;outline:none;';"
            + "var sb=document.createElement('button');sb.textContent='搜索';"
            + "sb.style.cssText='padding:8px 16px;border-radius:8px;border:none;background:#e91e63;color:#fff;font-size:13px;cursor:pointer;';"
            + "function doSearchClick(){var q=(inp.value||'').trim();if(q){mode='search';hasMore=false;abortLoad();searchGrid(q);}}"
            + "sb.addEventListener('click',doSearchClick);"
            + "inp.addEventListener('keydown',function(e){if(e.key==='Enter'){doSearchClick();}});"
            + "sr.appendChild(inp);sr.appendChild(sb);head.appendChild(sr);"
            + "}"
            + "function curTagsStr(){"
            + "var arr=[];Object.keys(curSel).forEach(function(k){(curSel[k]||[]).forEach(function(t){arr.push(t);});});"
            + "return arr.join(',');"
            + "}"
            + "function buildFilters(head){"
            + "var old=document.getElementById('__ltv_frows');if(old&&old.parentNode){old.parentNode.removeChild(old);}"
            + "var box=document.createElement('div');box.id='__ltv_frows';"
            + "box.style.cssText='margin-top:10px;';"
            + "var conf=CONF[curType];"
            + "Object.keys(conf).forEach(function(rowName){"
            + "if(!curSel[rowName]){curSel[rowName]=[];}"
            + "var row=document.createElement('div');"
            + "row.style.cssText='display:flex;gap:6px;align-items:flex-start;margin:6px 0;';"
            + "var lab=document.createElement('span');lab.textContent=rowName;"
            + "lab.style.cssText='color:#8a8aa0;font-size:12px;min-width:34px;line-height:26px;';"
            + "row.appendChild(lab);"
            + "var wrap=document.createElement('div');"
            + "wrap.style.cssText='display:flex;gap:6px;overflow-x:auto;white-space:nowrap;padding-bottom:2px;';"
            + "var allBtn=document.createElement('button');allBtn.textContent='全部';"
            + "var allOn=curSel[rowName].length===0;"
            + "allBtn.style.cssText='flex:0 0 auto;padding:4px 12px;border-radius:13px;font-size:12px;cursor:pointer;border:1px solid '+(allOn?'#e91e63':'#333')+';background:'+(allOn?'#e91e63':'#1e1e2c')+';color:'+(allOn?'#fff':'#bbb')+';';"
            + "allBtn.addEventListener('click',function(){curSel[rowName]=[];mode='filter';buildFilters(head);resetLoad();});"
            + "wrap.appendChild(allBtn);"
            + "conf[rowName].forEach(function(t){"
            + "var on=curSel[rowName].indexOf(t)>=0;"
            + "var b=document.createElement('button');b.textContent=t;"
            + "b.style.cssText='flex:0 0 auto;padding:4px 12px;border-radius:13px;font-size:12px;cursor:pointer;border:1px solid '+(on?'#e91e63':'#333')+';background:'+(on?'#e91e63':'#1e1e2c')+';color:'+(on?'#fff':'#bbb')+';';"
            + "b.addEventListener('click',function(){"
            + "var ix=curSel[rowName].indexOf(t);if(ix>=0){curSel[rowName].splice(ix,1);}else{curSel[rowName].push(t);}"
            + "mode='filter';buildFilters(head);resetLoad();});"
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
            + "function resetLoad(){pageStart=0;hasMore=true;mode='filter';retried=false;curTotal=0;rexSeq++;abortLoad();loadPage(false);}"
            + "function renderList(grid,list){"
            + "grid.innerHTML='';"
            + "list.forEach(function(it){grid.appendChild(makeCard(it));});"
            + "}"
            + "window.__ltvRexxCb=function(seq,ok,text){"
            + "if(parseInt(seq,10)!==rexSeq){return;}"
            + "loading=false;var p=ovlParts();if(!p){return;}"
            + "var list=[],total=0;"
            + "if(ok&&text){try{var d=JSON.parse(text);list=(d&&d.items)||[];total=(d&&d.total)||0;}catch(e){}}"
            + "if(!Array.isArray(list)){list=[];}"
            + "for(var i=list.length-1;i>=0;i--){if(!list[i]||!list[i].title){list.splice(i,1);}}"
            + "if(!list.length&&ok&&!retried){"
            + "retried=true;p.tip.textContent='加载不顺利，自动重试中…';"
            + "setTimeout(function(){loadPage(pendAppend);},900);return;"
            + "}"
            + "if(!list.length){loadDoubanFallback(pendAppend,pendCk,p);return;}"
            + "retried=false;curTotal=total;"
            + "if(!pendAppend){cache[pendCk]=list;renderList(p.grid,list);}"
            + "else{list.forEach(function(it){p.grid.appendChild(makeCard(it));});}"
            + "pageStart+=list.length;"
            + "hasMore=total>0?(pageStart<total):(list.length>=20);"
            + "p.tip.textContent=hasMore?'上滑加载更多':'没有更多了';"
            + "};"
            + "function loadDoubanFallback(append,ck,p){"
            + "var tag='热门';var ts=curTagsStr();"
            + "if(ts){var arr=ts.split(',');tag=arr[arr.length-1];}"
            + "var ctl=new AbortController();loadCtl=ctl;var sig=ctl.signal;"
            + "p.tip.textContent='豆瓣通道不顺，切换备用源…';"
            + "var url='/api/douban?type='+encodeURIComponent(curType)+'&tag='+encodeURIComponent(tag)+'&pageStart='+pageStart+'&pageSize=24';"
            + "fetch(url,{credentials:'include',signal:sig})"
            + ".then(function(r){return r.json();}).then(function(d){"
            + "var list=(d&&(d.list||d.subjects||d.items||d.data))||[];"
            + "if(!Array.isArray(list)){list=[];}"
            + "if(!list.length){hasMore=false;p.tip.textContent='该筛选暂无收录，换个条件试试';return;}"
            + "if(!append){cache[ck]=list;renderList(p.grid,list);}"
            + "else{list.forEach(function(it){p.grid.appendChild(makeCard(it));});}"
            + "hasMore=list.length>=24;pageStart+=list.length;"
            + "p.tip.textContent=hasMore?'上滑加载更多':'没有更多了';"
            + "}).catch(function(e){"
            + "if(e&&e.name==='AbortError'){return;}"
            + "p.tip.textContent='加载失败：'+esc(e.message||e);});"
            + "}"
            + "function loadPage(append){"
            + "if(loading){return;}loading=true;abortLoad();rexSeq++;"
            + "var p=ovlParts();"
            + "if(!p){loading=false;return;}"
            + "var tags=curTagsStr();"
            + "var ck=curType+'|'+tags;"
            + "if(!append&&cache[ck]){"
            + "renderList(p.grid,cache[ck]);"
            + "hasMore=cache[ck].length>=20;pageStart=cache[ck].length;"
            + "p.tip.textContent=hasMore?'上滑加载更多':'没有更多了';loading=false;return;"
            + "}"
            + "if(!append){p.grid.innerHTML='';}"
            + "p.tip.textContent='加载中…';"
            + "pendAppend=append;pendCk=ck;"
            + "var seq=rexSeq;"
            + "try{window.AndroidBridge.doubanFetch(curType,tags,String(pageStart),'20',String(seq));}"
            + "catch(e){rexSeq--;loadDoubanFallback(append,ck,p);}"
            + "}"
            + "function makeCard(it){"
            + "var t=it.title||it.name||'';"
            + "var img=it.poster||it.cover||it.img||'';"
            + "if(!img&&it.pic){img=(typeof it.pic==='object')?(it.pic.large||it.pic.normal||''):it.pic;}"
            + "if(img){img=img.replace(/img\\d+\\.doubanio\\.com/g,'img.doubanio.cmliussss.net');}"
            + "var rate=typeof it.rate==='object'?(it.rate.value||''):(it.rate||'');"
            + "if(!rate&&it.rating){rate=(typeof it.rating==='object')?(it.rating.value||''):it.rating;}"
            + "var card=document.createElement('div');card.style.cssText='cursor:pointer;';"
            + "card.innerHTML='<div style=\"position:relative\"><img src=\"'+esc(img)+'\" loading=\"lazy\" style=\"width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:8px;background:#222\">'"
            + "+(rate?'<span style=\"position:absolute;right:4px;top:4px;background:rgba(0,0,0,.7);color:#f5c518;font-size:11px;padding:1px 4px;border-radius:4px\">\\u2605'+esc(rate)+'</span>':'')+'</div>'"
            + "+'<div style=\"color:#ddd;font-size:12px;margin-top:4px;height:30px;line-height:15px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden\">'+esc(t)+'</div>';"
            + "card.addEventListener('click',function(){playTitle(t);});"
            + "return card;"
            + "}"
            + "function searchGrid(q){"
            + "var p=ovlParts();if(!p){return;}"
            + "p.grid.innerHTML='';p.tip.textContent='搜索中…';"
            + "xfetch('/api/search',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})})"
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
            + "+'<div style=\"color:#ddd;font-size:12px;margin-top:4px;height:30px;line-height:15px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden\">'+esc(t)+'</div>';"
            + "card.addEventListener('click',function(){if(src&&id){watch(src,id,t);}});"
            + "p.grid.appendChild(card);"
            + "});"
            + "}).catch(function(e){p.tip.textContent='搜索失败：'+esc(e.message||e);});"
            + "}"
            + "function playTitle(title){"
            + "if(!title){return;}"
            + "var p=ovlParts();"
            + "if(p){p.tip.textContent='正在找片源：'+title;}"
            + "xfetch('/api/search',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:title})})"
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
            + "try{"
            + "var isHome=(location.pathname==='/'||location.pathname==='/index.html');"
            + "var tries=parseInt(sessionStorage.getItem('__ltvHomeFix')||'0',10);"
            + "if(isHome&&tries<2){"
            + "var raw=localStorage.getItem('libretv-settings');"
            + "var obj=raw?JSON.parse(raw):null;"
            + "var st=obj&&obj.state?obj.state:null;"
            + "if(st&&st.recommendSource&&st.recommendSource!=='hot-list'){"
            + "st.recommendSource='hot-list';st.recommendSourceTouched=true;"
            + "localStorage.setItem('libretv-settings',JSON.stringify(obj));"
            + "sessionStorage.setItem('__ltvHomeFix',String(tries+1));"
            + "location.reload();"
            + "}else{sessionStorage.setItem('__ltvHomeFix','done');}"
            + "}"
            + "}catch(e){}"
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

        /**
         * 筛选页多标签推荐：网页 JS 调 AndroidBridge.doubanFetch(kind,tags,start,limit,seq)，
         * 原生线程直连豆瓣 rexxar 接口（绕过 WebView CORS），结果通过 window.__ltvRexxCb(seq,ok,json) 回调。
         */
        @JavascriptInterface
        public void doubanFetch(String kind, String tags, String start, String limit, final String seq) {
            final String k = "tv".equals(kind) ? "tv" : "movie";
            final String t = tags == null ? "" : tags;
            final String st = start == null ? "0" : start;
            final String lm = limit == null ? "20" : limit;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    final String json = doubanRexxar(k, t, st, lm);
                    final boolean ok = json != null;
                    String payload = ok ? json : "null";
                    String sq = (seq == null || seq.length() == 0) ? "0" : seq;
                    final String js = "window.__ltvRexxCb(" + sq + "," + ok + "," + payload + ");";
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (web != null) {
                                web.evaluateJavascript(js, null);
                            }
                        }
                    });
                }
            }).start();
        }
    }

    /** 原生直连豆瓣 rexxar 多标签推荐接口（手机 UA + Referer，无需登录；失败返回 null） */
    private static String doubanRexxar(String kind, String tags, String start, String limit) {
        HttpURLConnection conn = null;
        try {
            StringBuilder sb = new StringBuilder("https://m.douban.com/rexxar/api/v2/");
            sb.append(kind).append("/recommend?start=").append(start)
              .append("&limit=").append(limit);
            if (tags.length() > 0) {
                sb.append("&tags=").append(URLEncoder.encode(tags, "UTF-8"));
            }
            conn = (HttpURLConnection) new URL(sb.toString()).openConnection();
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setRequestProperty("User-Agent",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
                    + " (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1");
            conn.setRequestProperty("Referer", "https://m.douban.com/" + kind + "/");
            int code = conn.getResponseCode();
            if (code != 200) {
                return null;
            }
            BufferedReader br = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            char[] buf = new char[4096];
            int n;
            while ((n = br.read(buf)) != -1) {
                out.append(buf, 0, n);
            }
            br.close();
            return out.toString();
        } catch (Exception e) {
            return null;
        } finally {
            if (conn != null) {
                try {
                    conn.disconnect();
                } catch (Exception ignored) {
                }
            }
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
