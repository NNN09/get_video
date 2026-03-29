import asyncio
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from bilibili_api import user, video, Credential, sync


class BilibiliAPI:
    def __init__(self):
        self.credential = None
        if hasattr(config, 'COOKIE') and config.COOKIE:
            self._parse_cookie(config.COOKIE)
    
    def _parse_cookie(self, cookie_str: str):
        sessdata = ""
        bili_jct = ""
        buvid3 = ""
        
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key == 'SESSDATA':
                    sessdata = value
                elif key == 'bili_jct':
                    bili_jct = value
                elif key == 'buvid3':
                    buvid3 = value
        
        if sessdata and bili_jct:
            self.credential = Credential(
                sessdata=sessdata,
                bili_jct=bili_jct,
                buvid3=buvid3 if buvid3 else None
            )
            print("已加载Cookie认证")
    
    def get_user_info(self, uid: int) -> Optional[Dict]:
        try:
            u = user.User(uid=uid, credential=self.credential)
            info = sync(u.get_user_info())
            
            return {
                "uid": uid,
                "name": info.get("name", ""),
                "face": info.get("face", ""),
                "sign": info.get("sign", ""),
                "level": info.get("level", 0),
                "sex": info.get("sex", ""),
                "coins": info.get("coins", 0),
                "fans": info.get("fans", -1),
                "attention": info.get("attention", -1),
            }
        except Exception as e:
            print(f"获取用户信息失败: {e}")
            return None
    
    def get_user_videos(self, uid: int, page: int = 1, page_size: int = 30) -> Optional[Dict]:
        try:
            u = user.User(uid=uid, credential=self.credential)
            result = sync(u.get_videos(pn=page, ps=page_size))
            
            videos = []
            for v in result.get("list", {}).get("vlist", []):
                videos.append({
                    "bvid": v.get("bvid"),
                    "title": v.get("title"),
                    "description": v.get("description", ""),
                    "author": v.get("author"),
                    "mid": v.get("mid"),
                    "created": v.get("created"),
                    "length": v.get("length"),
                    "play": v.get("play"),
                    "video_review": v.get("comment"),
                    "pic": v.get("pic"),
                    "duration": v.get("duration"),
                })
            
            tlist = result.get("list", {}).get("tlist", {})
            total = sum(item.get("count", 0) for item in tlist.values()) if tlist else len(videos)
            has_more = len(videos) == page_size
            
            return {
                "videos": videos,
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": has_more,
            }
        except Exception as e:
            print(f"获取用户视频列表失败: {e}")
            return None
    
    def get_video_info(self, bvid: str) -> Optional[Dict]:
        try:
            v = video.Video(bvid=bvid, credential=self.credential)
            info = sync(v.get_info())
            
            pages = []
            for page_info in info.get("pages", []):
                pages.append({
                    "cid": page_info.get("cid"),
                    "page": page_info.get("page"),
                    "part": page_info.get("part"),
                    "duration": page_info.get("duration"),
                })
            
            return {
                "bvid": info.get("bvid"),
                "aid": info.get("aid"),
                "title": info.get("title"),
                "pic": info.get("pic"),
                "description": info.get("desc"),
                "duration": info.get("duration"),
                "owner": {
                    "mid": info.get("owner", {}).get("mid"),
                    "name": info.get("owner", {}).get("name"),
                    "face": info.get("owner", {}).get("face"),
                },
                "stat": {
                    "view": info.get("stat", {}).get("view"),
                    "like": info.get("stat", {}).get("like"),
                    "coin": info.get("stat", {}).get("coin"),
                    "favorite": info.get("stat", {}).get("favorite"),
                    "share": info.get("stat", {}).get("share"),
                    "danmaku": info.get("stat", {}).get("danmaku"),
                },
                "pages": pages,
                "cid": info.get("cid"),
                "pubdate": info.get("pubdate"),
                "tname": info.get("tname"),
            }
        except Exception as e:
            print(f"获取视频信息失败: {e}")
            return None
    
    def get_video_playurl(self, bvid: str, cid: int, quality: int = 80) -> Optional[Dict]:
        try:
            v = video.Video(bvid=bvid, credential=self.credential)
            result = sync(v.get_download_url(cid=cid))
            
            dash = result.get("dash")
            
            response = {
                "quality": result.get("quality"),
                "quality_description": config.QUALITY_MAP.get(result.get("quality"), "未知"),
                "timelength": result.get("timelength"),
                "accept_quality": result.get("accept_quality", []),
                "accept_description": [
                    config.QUALITY_MAP.get(q, "未知") for q in result.get("accept_quality", [])
                ],
            }
            
            if dash:
                video_list = dash.get("video", [])
                audio_list = dash.get("audio", [])
                
                response["format"] = "dash"
                response["video"] = [
                    {
                        "id": v.get("id"),
                        "base_url": v.get("baseUrl") or v.get("base_url"),
                        "backup_url": v.get("backupUrl") or v.get("backup_url"),
                        "bandwidth": v.get("bandwidth"),
                        "mimeType": v.get("mimeType") or v.get("mime_type"),
                        "codecs": v.get("codecs"),
                        "width": v.get("width"),
                        "height": v.get("height"),
                    }
                    for v in video_list
                ]
                response["audio"] = [
                    {
                        "id": a.get("id"),
                        "base_url": a.get("baseUrl") or a.get("base_url"),
                        "backup_url": a.get("backupUrl") or a.get("backup_url"),
                        "bandwidth": a.get("bandwidth"),
                        "mimeType": a.get("mimeType") or a.get("mime_type"),
                        "codecs": a.get("codecs"),
                    }
                    for a in audio_list
                ]
            
            return response
        except Exception as e:
            print(f"获取播放地址失败: {e}")
            return None
    
    def get_all_user_videos(self, uid: int, max_videos: int = None) -> List[Dict]:
        import time
        import random
        
        all_videos = []
        page = 1
        total_count = None

        while True:
            print(f"正在获取第 {page} 页视频...")
            result = self.get_user_videos(uid, page=page)

            if not result or not result.get("videos"):
                break

            if total_count is None:
                total_count = result.get("total", 0)
                print(f"用户共有 {total_count} 个视频")

            all_videos.extend(result["videos"])
            print(f"已获取 {len(all_videos)}/{total_count} 个视频")

            if max_videos and len(all_videos) >= max_videos:
                all_videos = all_videos[:max_videos]
                break

            if not result.get("has_more"):
                break

            page += 1
            time.sleep(random.uniform(1, 2))

        return all_videos


if __name__ == "__main__":
    api = BilibiliAPI()
    
    print("测试获取用户信息...")
    user_info = api.get_user_info(517327498)
    if user_info:
        print(f"用户名: {user_info['name']}")
        print(f"等级: Lv{user_info['level']}")
    
    print("\n测试获取视频列表...")
    videos = api.get_user_videos(517327498, page=1, page_size=5)
    if videos:
        print(f"获取到 {len(videos['videos'])} 个视频")
        for v in videos['videos'][:3]:
            print(f"  - {v['bvid']}: {v['title']}")
