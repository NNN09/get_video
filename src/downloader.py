import os
import re
import subprocess
import shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import requests
from tqdm import tqdm

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.utils import random_delay, RateLimiter, get_headers


class VideoDownloader:
    def __init__(self, api, save_dir: str = None):
        self.api = api
        self.save_dir = save_dir or config.STATIC_DIR
        self.rate_limiter = RateLimiter()
        self.session = requests.Session()
        self.session.headers.update(get_headers(referer="https://www.bilibili.com"))
        
        Path(self.save_dir).mkdir(parents=True, exist_ok=True)
    
    def sanitize_filename(self, filename: str, max_length: int = 200) -> str:
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
    
    def select_best_quality(
        self,
        available_qualities: List[int],
        preferred_quality: int = 80
    ) -> int:
        if preferred_quality in available_qualities:
            return preferred_quality
        
        sorted_qualities = sorted(available_qualities, reverse=True)
        
        if sorted_qualities:
            return sorted_qualities[0]
        
        return 80
    
    def download_file(
        self,
        url: str,
        filepath: str,
        title: str = "文件"
    ) -> bool:
        try:
            downloaded_size = 0
            if os.path.exists(filepath):
                downloaded_size = os.path.getsize(filepath)
            
            headers = dict(self.session.headers)
            headers["Referer"] = "https://www.bilibili.com"
            if downloaded_size > 0:
                headers["Range"] = f"bytes={downloaded_size}-"
            
            response = self.session.get(
                url,
                headers=headers,
                stream=True,
                timeout=30
            )
            
            if response.status_code == 416:
                return True
            
            if response.status_code not in [200, 206]:
                print(f"下载失败: HTTP {response.status_code}")
                return False
            
            total_size = int(response.headers.get('content-length', 0))
            if downloaded_size > 0 and response.status_code == 200:
                downloaded_size = 0
                total_size = int(response.headers.get('content-length', 0))
            
            if downloaded_size > 0:
                total_size += downloaded_size
            
            mode = 'ab' if downloaded_size > 0 else 'wb'
            
            desc = f"下载 {title[:20]}..."
            if downloaded_size > 0:
                desc = f"续传 {title[:20]}..."
            
            with open(filepath, mode) as f:
                with tqdm(
                    total=total_size,
                    initial=downloaded_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=desc
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            return True
            
        except Exception as e:
            print(f"下载文件失败: {e}")
            return False
    
    def check_ffmpeg(self) -> bool:
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def merge_video_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str
    ) -> bool:
        if self.check_ffmpeg():
            return self._merge_with_ffmpeg(video_path, audio_path, output_path)
        else:
            return self._merge_with_moviepy(video_path, audio_path, output_path)
    
    def _merge_with_ffmpeg(
        self,
        video_path: str,
        audio_path: str,
        output_path: str
    ) -> bool:
        try:
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-y',
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return True
            else:
                print(f"ffmpeg合并失败: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            print("ffmpeg合并超时")
            return False
        except Exception as e:
            print(f"ffmpeg合并失败: {e}")
            return False
    
    def _merge_with_moviepy(
        self,
        video_path: str,
        audio_path: str,
        output_path: str
    ) -> bool:
        video = None
        audio = None
        final = None
        try:
            from moviepy import VideoFileClip, AudioFileClip
            import warnings
            warnings.filterwarnings("ignore")
            
            print("使用moviepy合并视频（较慢，建议安装ffmpeg）...")
            
            video = VideoFileClip(video_path)
            audio = AudioFileClip(audio_path)
            
            if audio.duration > video.duration:
                audio = audio.subclipped(0, video.duration)
            
            final = video.with_audio(audio)
            final.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                audio_bitrate='192k'
            )
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                print("合并后文件无效")
                return False
                
        except Exception as e:
            print(f"moviepy合并失败: {e}")
            return False
        finally:
            try:
                if final:
                    final.close()
                if video:
                    video.close()
                if audio:
                    audio.close()
            except Exception:
                pass
    
    def download_video(
        self,
        bvid: str,
        title: str,
        preferred_quality: int = 80
    ) -> Tuple[bool, str]:
        print(f"\n开始下载: {title} ({bvid})")
        
        video_info = self.api.get_video_info(bvid)
        if not video_info:
            return False, f"获取视频信息失败: {bvid}"
        
        cid = video_info.get("cid")
        if not cid:
            pages = video_info.get("pages", [])
            if pages:
                cid = pages[0].get("cid")
            else:
                return False, f"无法获取视频cid: {bvid}"
        
        playurl = self.api.get_video_playurl(bvid, cid, quality=preferred_quality)
        if not playurl:
            return False, f"获取播放地址失败: {bvid}"
        
        sanitized_title = self.sanitize_filename(title)
        
        return self._download_dash(playurl, sanitized_title, bvid, preferred_quality)
    
    def _download_dash(
        self,
        playurl: Dict,
        sanitized_title: str,
        bvid: str,
        preferred_quality: int = 80
    ) -> Tuple[bool, str]:
        video_list = playurl.get("video", [])
        audio_list = playurl.get("audio", [])
        
        if not video_list:
            return False, f"无可用的视频流: {bvid}"
        
        available_qualities = playurl.get("accept_quality", [])
        selected_quality = self.select_best_quality(available_qualities, preferred_quality)
        
        video_candidates = [v for v in video_list if v.get("id") == selected_quality]
        if not video_candidates:
            video_candidates = video_list
        
        video_info = None
        for v in video_candidates:
            codecs = v.get("codecs", "")
            if "avc1" in codecs.lower():
                video_info = v
                print(f"选择AVC编码视频流")
                break
        
        if not video_info:
            for v in video_candidates:
                codecs = v.get("codecs", "")
                if "av01" not in codecs.lower() and "hev1" not in codecs.lower():
                    video_info = v
                    break
        
        if not video_info:
            video_info = video_candidates[0]
            codecs = video_info.get("codecs", "")
            if "hev1" in codecs.lower():
                print(f"注意: 仅HEVC编码可用，可能需要安装HEVC扩展")
        
        if video_info.get("id") != selected_quality:
            print(f"清晰度降级: {config.QUALITY_MAP.get(preferred_quality, preferred_quality)} -> {config.QUALITY_MAP.get(video_info.get('id'), video_info.get('id'))}")
        
        video_url = video_info.get("base_url")
        backup_urls = video_info.get("backup_url", [])
        
        audio_url = None
        if audio_list:
            best_audio = None
            for a in audio_list:
                if best_audio is None or a.get("id", 0) > best_audio.get("id", 0):
                    best_audio = a
            
            if best_audio:
                audio_url = best_audio.get("base_url")
                if not audio_url and best_audio.get("backup_url"):
                    audio_url = best_audio["backup_url"][0]
                print(f"选择音频流: id={best_audio.get('id')}")
        
        temp_dir = os.path.join(self.save_dir, "temp")
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        
        video_temp_path = os.path.join(temp_dir, f"{sanitized_title}_{bvid}_video.m4s")
        audio_temp_path = os.path.join(temp_dir, f"{sanitized_title}_{bvid}_audio.m4s")
        output_path = os.path.join(self.save_dir, f"{sanitized_title}.mp4")
        
        if os.path.exists(output_path):
            print(f"文件已存在，跳过: {output_path}")
            return True, output_path
        
        random_delay()
        
        success = self.download_file(video_url, video_temp_path, f"{sanitized_title}[视频]")
        if not success and backup_urls:
            for backup_url in backup_urls:
                random_delay()
                success = self.download_file(backup_url, video_temp_path, f"{sanitized_title}[视频]")
                if success:
                    break
        
        if not success:
            return False, f"视频流下载失败: {bvid}"
        
        if audio_url:
            random_delay()
            success = self.download_file(audio_url, audio_temp_path, f"{sanitized_title}[音频]")
            
            if success:
                print("正在合并视频和音频...")
                if self.merge_video_audio(video_temp_path, audio_temp_path, output_path):
                    print(f"下载完成: {output_path}")
                    self._cleanup_temp_files(video_temp_path, audio_temp_path)
                    return True, output_path
                else:
                    output_video_only = os.path.join(self.save_dir, f"{sanitized_title}_video_only.mp4")
                    if os.path.exists(video_temp_path):
                        shutil.move(video_temp_path, output_video_only)
                    self._cleanup_temp_files(audio_temp_path)
                    return False, f"合并失败，仅视频文件: {output_video_only}"
            else:
                output_video_only = os.path.join(self.save_dir, f"{sanitized_title}_video_only.mp4")
                if os.path.exists(video_temp_path):
                    shutil.move(video_temp_path, output_video_only)
                self._cleanup_temp_files(audio_temp_path)
                print(f"音频下载失败，仅保存视频: {output_video_only}")
                return True, output_video_only
        else:
            output_video_only = os.path.join(self.save_dir, f"{sanitized_title}.mp4")
            shutil.move(video_temp_path, output_video_only)
            print(f"下载完成(仅视频): {output_video_only}")
            return True, output_video_only
    
    def _cleanup_temp_files(self, *files):
        for f in files:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
    
    def _download_legacy(
        self,
        playurl: Dict,
        sanitized_title: str,
        bvid: str
    ) -> Tuple[bool, str]:
        url_list = playurl.get("url", [])
        
        if not url_list:
            return False, f"无可用的下载链接: {bvid}"
        
        output_path = os.path.join(self.save_dir, f"{sanitized_title}.mp4")
        
        if os.path.exists(output_path):
            print(f"文件已存在，跳过: {output_path}")
            return True, output_path
        
        if len(url_list) == 1:
            random_delay()
            url = url_list[0].get("url")
            success = self.download_file(url, output_path, sanitized_title)
            if success:
                print(f"下载完成: {output_path}")
                return True, output_path
            else:
                return False, f"下载失败: {bvid}"
        else:
            temp_dir = os.path.join(self.save_dir, "temp")
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            
            part_files = []
            for i, url_info in enumerate(url_list):
                url = url_info.get("url")
                part_path = os.path.join(temp_dir, f"{sanitized_title}_{bvid}_part{i}.flv")
                
                random_delay()
                success = self.download_file(url, part_path, f"{sanitized_title}_part{i}")
                if not success:
                    for part_file in part_files:
                        if os.path.exists(part_file):
                            os.remove(part_file)
                    return False, f"分段{i}下载失败: {bvid}"
                
                part_files.append(part_path)
            
            print("正在合并分段...")
            try:
                with open(output_path, 'wb') as outfile:
                    for part_file in part_files:
                        with open(part_file, 'rb') as infile:
                            outfile.write(infile.read())
                        os.remove(part_file)
                
                print(f"下载完成: {output_path}")
                return True, output_path
            except Exception as e:
                return False, f"合并分段失败: {e}"


def download_all_videos(
    videos: List[Dict],
    user_name: str,
    api,
    preferred_quality: int = 80
) -> Dict:
    user_dir = os.path.join(config.STATIC_DIR, VideoDownloader(None).sanitize_filename(user_name))
    
    downloader = VideoDownloader(api, save_dir=user_dir)
    
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
        "total": len(videos)
    }
    
    videos_to_download = [v for v in videos if not v.get('exists', False)]
    skipped_videos = [v for v in videos if v.get('exists', False)]
    
    for video in skipped_videos:
        results["skipped"].append({
            "bvid": video.get("bvid"),
            "title": video.get("title", "未知标题")
        })
    
    print(f"\n开始批量下载，共 {len(videos)} 个视频")
    print(f"已存在跳过: {len(skipped_videos)} 个")
    print(f"待下载: {len(videos_to_download)} 个")
    print(f"保存目录: {user_dir}")
    
    with downloader.rate_limiter:
        for i, video in enumerate(videos_to_download, 1):
            bvid = video.get("bvid")
            title = video.get("title", "未知标题")
            
            print(f"\n[{i}/{len(videos_to_download)}] 处理: {title}")
            
            try:
                success, message = downloader.download_video(bvid, title, preferred_quality)
                
                if success:
                    results["success"].append({
                        "bvid": bvid,
                        "title": title,
                        "path": message
                    })
                else:
                    results["failed"].append({
                        "bvid": bvid,
                        "title": title,
                        "error": message
                    })
                    
            except Exception as e:
                print(f"下载异常: {e}")
                results["failed"].append({
                    "bvid": bvid,
                    "title": title,
                    "error": str(e)
                })
            
            random_delay()
    
    temp_dir = os.path.join(user_dir, "temp")
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            print("已清理临时文件夹")
        except Exception as e:
            print(f"清理临时文件夹失败: {e}")
    
    print("\n" + "="*50)
    print("下载完成!")
    print(f"成功: {len(results['success'])} 个")
    print(f"失败: {len(results['failed'])} 个")
    print(f"跳过: {len(results['skipped'])} 个")
    
    if results["failed"]:
        print("\n失败列表:")
        for item in results["failed"]:
            print(f"  - [{item['bvid']}] {item['title']}: {item['error']}")
    
    if results["skipped"]:
        print("\n跳过列表:")
        for item in results["skipped"]:
            print(f"  - [{item['bvid']}] {item['title']}")
    
    return results


if __name__ == "__main__":
    from src.bilibili_api import BilibiliAPI
    
    api = BilibiliAPI()
    
    print("测试下载单个视频...")
    downloader = VideoDownloader(api)
    success, result = downloader.download_video("BV1xx411c7mD", "测试视频", preferred_quality=80)
    
    if success:
        print(f"下载成功: {result}")
    else:
        print(f"下载失败: {result}")
