#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 easytier-core 命令检测 EasyTier 节点连通性
通过监控命令输出来判断节点是否可用
"""

import os
import sys
import subprocess
import time
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# 设置 Windows 终端 UTF-8 编码
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    sys.stdout.reconfigure(encoding='utf-8')

# easytier-core 可执行文件路径
# Windows 优先使用 .exe 版本
if sys.platform == 'win32':
    EASYTIER_CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                  'bin', 'easytier-core.exe')
    # 如果 .exe 不存在，尝试无扩展名版本
    if not os.path.exists(EASYTIER_CORE):
        EASYTIER_CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                      'bin', 'easytier-core')
else:
    EASYTIER_CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                  'bin', 'easytier-core')

# 检测超时时间（秒）
TIMEOUT = 10

# 成功关键字
SUCCESS_KEYWORDS = ['new peer added', 'peer_id:']

# 失败关键字
FAIL_KEYWORDS = ['connect to peer error', 'error', 'failed']


def parse_peer_url(url: str) -> dict:
    """解析 peer URL"""
    match = re.match(r'^(tcp|udp)://([^:]+):(\d+)$', url.strip(), re.IGNORECASE)
    if match:
        return {
            "protocol": match.group(1).upper(),
            "host": match.group(2),
            "port": int(match.group(3)),
            "original": url.strip()
        }
    return None


def check_peer_with_easytier(peer_url: str) -> dict:
    """
    使用 easytier-core 命令检测单个节点
    
    返回: {
        "address": 节点地址,
        "success": 是否成功,
        "latency": 延迟(毫秒),
        "output": 输出日志,
        "error": 错误信息
    }
    """
    result = {
        "address": peer_url,
        "success": False,
        "latency": None,
        "output": [],
        "error": None
    }
    
    # 构建命令
    cmd = [
        EASYTIER_CORE,
        '--console-log-level', 'ERROR',
        '--no-listener',
        '-p', peer_url
    ]
    
    start_time = time.time()
    
    try:
        # 启动进程
        if sys.platform == 'win32':
            # Windows: 使用 CREATE_NEW_PROCESS_GROUP 来允许终止进程树
            print(" ".join(cmd))
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
        
        # 读取输出并监控关键字
        output_lines = []
        success_detected = False
        fail_detected = False
        
        while True:
            elapsed = time.time() - start_time
            
            # 超时检查
            if elapsed > TIMEOUT:
                result["error"] = "检测超时"
                break
            
            # 非阻塞读取输出
            import select
            if sys.platform != 'win32':
                readable, _, _ = select.select([process.stdout], [], [], 0.1)
                if readable:
                    line = process.stdout.readline()
                    if line:
                        line = line.strip()
                        output_lines.append(line)
                        
                        # 检查成功关键字
                        if any(keyword in line.lower() for keyword in SUCCESS_KEYWORDS):
                            result["success"] = True
                            result["latency"] = round((time.time() - start_time) * 1000, 2)
                            success_detected = True
                            break
                        
                        # 检查失败关键字
                        if any(keyword in line.lower() for keyword in FAIL_KEYWORDS):
                            result["error"] = f"连接失败: {line}"
                            fail_detected = True
                            break
            else:
                # Windows: 使用不同的读取方式
                try:
                    import msvcrt
                    if msvcrt.kbhit():
                        line = process.stdout.readline()
                        if line:
                            line = line.strip()
                            output_lines.append(line)
                            
                            if any(keyword in line.lower() for keyword in SUCCESS_KEYWORDS):
                                result["success"] = True
                                result["latency"] = round((time.time() - start_time) * 1000, 2)
                                success_detected = True
                                break
                            
                            if any(keyword in line.lower() for keyword in FAIL_KEYWORDS):
                                result["error"] = f"连接失败: {line}"
                                fail_detected = True
                                break
                except:
                    pass
                
                # Windows 简单轮询
                time.sleep(0.1)
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    output_lines.append(line)
                    
                    if any(keyword in line.lower() for keyword in SUCCESS_KEYWORDS):
                        result["success"] = True
                        result["latency"] = round((time.time() - start_time) * 1000, 2)
                        success_detected = True
                        break
                    
                    if any(keyword in line.lower() for keyword in FAIL_KEYWORDS):
                        result["error"] = f"连接失败: {line}"
                        fail_detected = True
                        break
            
            # 检查进程是否已结束
            if process.poll() is not None:
                break
        
        # 终止进程
        try:
            if sys.platform == 'win32':
                import signal
                os.kill(process.pid, signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
            
            # 等待进程结束
            process.wait(timeout=2)
        except:
            try:
                process.kill()
            except:
                pass
        
        result["output"] = output_lines
        
        # 如果没有检测到明确的成功或失败
        if not success_detected and not fail_detected:
            if result["latency"] is None:
                result["error"] = "未检测到连接结果"
        
        return result
        
    except FileNotFoundError:
        result["error"] = f"找不到 easytier-core: {EASYTIER_CORE}"
        return result
    except Exception as e:
        result["error"] = f"执行错误: {str(e)}"
        return result


def main():
    """主函数"""
    # 检查 easytier-core 是否存在
    if not os.path.exists(EASYTIER_CORE):
        print(f"错误: 找不到 easytier-core: {EASYTIER_CORE}")
        print("请确保 easytier-core 在 bin 目录中")
        sys.exit(1)
    
    # 节点列表文件路径
    peer_list_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                   'peers', 'peer-list.txt')
    peer_meta_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                   'peers', 'peer-meta.json')
    
    # 读取节点列表
    try:
        with open(peer_list_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"错误: 找不到文件 {peer_list_path}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 读取文件失败 - {e}")
        sys.exit(1)
    
    # 解析所有节点
    peers = []
    for line in lines:
        peer_info = parse_peer_url(line)
        if peer_info:
            peers.append(peer_info["original"])
    
    if not peers:
        print("没有找到有效的 peer 地址")
        sys.exit(0)
    
    print("=" * 60)
    print("    EasyTier Peer 连通性检测 (使用 easytier-core)")
    print("=" * 60)
    print(f"检测节点数: {len(peers)}")
    print(f"超时时间: {TIMEOUT} 秒")
    print()
    
    results = []
    
    # 串行检测（因为 easytier-core 可能会占用端口等资源）
    for peer_url in peers:
        print(f"检测: {peer_url} ... ", end='', flush=True)
        result = check_peer_with_easytier(peer_url)
        results.append(result)
        
        if result["success"]:
            print(f"✓ 连通 ({result['latency']}ms)")
        else:
            error = result.get('error', '未知错误')
            print(f"✗ 不通 [{error}]")
    
    # 统计结果
    connected = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print()
    print("=" * 60)
    print("统计:")
    print(f"  连通: {len(connected)} / {len(results)}")
    print(f"  不通: {len(failed)} / {len(results)}")
    print("=" * 60)
    
    # 输出可用的地址
    if connected:
        print()
        print("可用的地址列表:")
        available_peers = []
        indexs = {"tcp": 0, "udp": 0}
        
        for r in sorted(connected, key=lambda x: x["latency"] if x["latency"] else float('inf')):
            latency_str = f" ({r['latency']}ms)" if r["latency"] else ""
            print(f"  {r['address']}{latency_str}")
            
            # 解析协议类型
            match = re.match(r'^(tcp|udp)://', r['address'], re.IGNORECASE)
            if match:
                schema = match.group(1).lower()
                indexs[schema] += 1
                
                # 保存到文件
                # 使用相对路径，基于项目根目录
                file_path = f"/peers/{schema}-{indexs[schema]}.txt"
                file_relative_path = f"..{file_path}"
                os.makedirs(os.path.dirname(file_relative_path), exist_ok=True)
                with open(file_relative_path, 'w', encoding='utf-8') as f:
                    f.write(r['address'])
                
                available_peers.append({"url": r['address'], "txt": file_path})
        
        # 保存元数据
        with open(peer_meta_path, 'w', encoding='utf-8') as f:
            json.dump(available_peers, f, ensure_ascii=False, indent=2)
    
    # 输出不可用的地址
    if failed:
        print()
        print("不可用的地址列表:")
        for r in failed:
            error_str = f" [{r['error']}]" if r['error'] else ""
            print(f"  {r['address']}{error_str}")


if __name__ == "__main__":
    main()
