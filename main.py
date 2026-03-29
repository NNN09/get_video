import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.bilibili_api import BilibiliAPI
from src.downloader import VideoDownloader, download_all_videos
import config


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    sanitized = sanitized.strip()
    sanitized = re.sub(r'\.{2,}', '.', sanitized)
    sanitized = sanitized.strip('.')
    
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized


def check_video_exists(title: str, user_name: str) -> bool:
    user_dir = os.path.join(config.STATIC_DIR, sanitize_filename(user_name))
    if not os.path.exists(user_dir):
        return False
    
    sanitized_title = sanitize_filename(title)
    video_path = os.path.join(user_dir, f"{sanitized_title}.mp4")
    return os.path.exists(video_path)


def print_welcome():
    print("=" * 60)
    print("          Bilibili 视频批量下载工具")
    print("=" * 60)
    print()


def select_quality():
    print("\n可选清晰度:")
    print("-" * 40)
    quality_options = [
        (127, "8K 超高清"),
        (126, "杜比视界"),
        (125, "HDR 真彩"),
        (120, "4K 超清"),
        (116, "1080P60 大会员"),
        (112, "1080P+ 大会员"),
        (80, "1080P 高清"),
        (74, "720P60"),
        (64, "720P 高清"),
        (32, "480P 清晰"),
        (16, "360P 流畅"),
    ]
    
    for i, (qn, desc) in enumerate(quality_options, 1):
        print(f"  {i}. {desc} (qn={qn})")
    
    print("-" * 40)
    
    while True:
        try:
            choice = input("请选择清晰度 (输入序号，默认7-1080P): ").strip()
            
            if not choice:
                return 80
            
            idx = int(choice)
            if 1 <= idx <= len(quality_options):
                qn, desc = quality_options[idx - 1]
                print(f"已选择: {desc}")
                return qn
            else:
                print(f"请输入 1-{len(quality_options)} 之间的数字")
        except ValueError:
            print("请输入有效的数字")


def input_user_id():
    api = BilibiliAPI()
    
    while True:
        try:
            user_input = input("请输入Bilibili用户ID (输入 q 退出): ").strip()
            
            if user_input.lower() == 'q':
                print("已退出程序。")
                sys.exit(0)
            
            if not user_input.isdigit():
                print("错误: 用户ID必须为数字，请重新输入。")
                continue
            
            uid = int(user_input)
            
            print(f"\n正在验证用户 {uid} ...")
            user_info = api.get_user_info(uid)
            
            if not user_info:
                print(f"错误: 用户 {uid} 不存在或无法访问，请重新输入。")
                continue
            
            print(f"\n用户验证成功!")
            print(f"  用户名: {user_info['name']}")
            print(f"  等级:   Lv{user_info['level']}")
            if user_info.get('sign'):
                print(f"  签名:   {user_info['sign'][:50]}...")
            print()
            
            return uid, user_info
            
        except KeyboardInterrupt:
            print("\n\n用户中断输入。")
            sys.exit(0)
        except Exception as e:
            print(f"错误: {e}")
            continue


def fetch_and_display_videos(uid, user_name):
    api = BilibiliAPI()
    
    print("正在获取视频列表...")
    print("-" * 60)
    
    try:
        videos = api.get_all_user_videos(uid)
        
        if not videos:
            print("该用户没有公开视频。")
            return []
        
        for video in videos:
            title = video.get('title', '')
            video['exists'] = check_video_exists(title, user_name)
        
        exist_count = sum(1 for v in videos if v.get('exists'))
        print(f"\n共找到 {len(videos)} 个视频 (已存在: {exist_count} 个):\n")
        print(f"{'序号':<6} {'BV号':<14} {'标题':<26} {'时长':<10} {'播放量':<10} {'状态':<8}")
        print("-" * 90)
        
        for i, video in enumerate(videos, 1):
            bvid = video.get('bvid', 'N/A')
            title = video.get('title', '未知标题')[:24]
            length = video.get('length', 'N/A')
            play = video.get('play', 0)
            exists = video.get('exists', False)
            
            if isinstance(play, int):
                if play >= 10000:
                    play_str = f"{play/10000:.1f}万"
                else:
                    play_str = str(play)
            else:
                play_str = str(play)
            
            status = "已存在" if exists else ""
            print(f"{i:<6} {bvid:<14} {title:<26} {length:<10} {play_str:<10} {status:<8}")
        
        print("-" * 90)
        print(f"\n视频总数: {len(videos)} (待下载: {len(videos) - exist_count} 个)")
        print()
        
        return videos
        
    except Exception as e:
        print(f"获取视频列表失败: {e}")
        return []


def confirm_download():
    while True:
        try:
            choice = input("是否开始下载所有视频? (yes/no): ").strip().lower()
            
            if choice in ['yes', 'y']:
                return True
            elif choice in ['no', 'n']:
                return False
            else:
                print("请输入 yes 或 no")
                
        except KeyboardInterrupt:
            print("\n用户取消操作。")
            return False


def start_download(uid, user_name, videos, quality=80):
    if not videos:
        print("没有可下载的视频。")
        return
    
    print("\n" + "=" * 60)
    print("开始下载")
    print("=" * 60)
    
    api = BilibiliAPI()
    results = download_all_videos(videos, user_name, api, preferred_quality=quality)
    
    print("\n" + "=" * 60)
    print("下载完成")
    print("=" * 60)
    print(f"总计: {results['total']} 个视频")
    print(f"成功: {len(results['success'])} 个")
    print(f"失败: {len(results['failed'])} 个")
    print()


def main():
    try:
        print_welcome()
        
        uid, user_info = input_user_id()
        
        videos = fetch_and_display_videos(uid, user_info['name'])
        
        if not videos:
            print("没有找到视频，程序结束。")
            return
        
        if confirm_download():
            quality = select_quality()
            start_download(uid, user_info['name'], videos, quality)
        else:
            print("已取消下载。")
        
        print("程序执行完毕。")
        
    except KeyboardInterrupt:
        print("\n\n用户中断程序执行。")
        sys.exit(0)
    except Exception as e:
        print(f"\n程序发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
