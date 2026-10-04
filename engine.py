import os
import subprocess
import struct
import shutil
import random

def check_tools():
    """Vérifie la présence de FFmpeg et FFprobe"""
    if not shutil.which("ffmpeg") and not os.path.exists("ffmpeg.exe"): return False
    if not shutil.which("ffprobe") and not os.path.exists("ffprobe.exe"): return False
    return True

def run_cmd(cmd, step_name, log_cb):
    log_cb(f"\n[+] {step_name}...")
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        log_cb(f"[CRASH] {step_name} a échoué.")
        raise Exception("Command failed")

def mosh_avi(input_avi, output_avi, timeline_events, log_cb):
    with open(input_avi, 'rb') as f_in, open(output_avi, 'wb') as f_out:
        
        buffer = b''
        while True:
            chunk = f_in.read(4096)
            if not chunk: raise Exception("AVI invalide : balise 'movi' introuvable")
            buffer += chunk
            idx = buffer.find(b'movi')
            if idx != -1:
                f_out.write(buffer[:idx+4])
                f_in.seek(f_in.tell() - len(buffer) + idx + 4)
                break

        last_p_frame = None
        last_i_frame = None
        history_buffer = []
        
        stats = {'i_drop': 0, 'i_shift': 0, 'generated': 0}
        frame_index = 0
        
        for ev in timeline_events: 
            ev['triggered'] = False
            ev['state'] = {}
            
        while True:
            header = f_in.read(8)
            if len(header) < 8:
                f_out.write(header)
                break
                
            chunk_id = header[:4]
            
            if chunk_id == b'idx1':
                f_out.write(header)
                while True:
                    rem = f_in.read(65536)
                    if not rem: break
                    f_out.write(rem)
                break
                
            chunk_size = struct.unpack('<I', header[4:8])[0]
            pad = chunk_size % 2
            
            chunk_data = f_in.read(chunk_size + pad)
            if len(chunk_data) < (chunk_size + pad):
                f_out.write(header)
                f_out.write(chunk_data)
                break
            
            if chunk_id in (b'00dc', b'01dc'):
                actual_data = chunk_data[:chunk_size]
                pad_bytes = chunk_data[chunk_size:]
                
                idx = actual_data.find(b'\x00\x00\x01\xb6') 
                
                if idx != -1 and len(actual_data) > idx + 4:
                    frame_type = (actual_data[idx+4] >> 6) & 0x03
                    frame_index += 1
                    
                    active_events = [ev for ev in timeline_events if ev['frame'] <= frame_index < ev['frame'] + ev['dur']]
                    
                    # DÉTECTION DE COUPURE
                    is_cut = False
                    if frame_type == 0:
                        is_cut = True
                    elif frame_type == 1 and history_buffer:
                        avg_p_size = sum(len(f) for f in history_buffer) / max(1, len(history_buffer))
                        # Si la frame est 4x plus grosse que la moyenne et dépasse 15KB -> Cut déguisé
                        if chunk_size > (avg_p_size * 4) and chunk_size > 15000:
                            is_cut = True

                    # ACTIONS DE TRANSITION
                    action = None
                    if is_cut:
                        trans_actifs = [e['type'] for e in active_events if '[TRANSITION]' in e['type']]
                        if any('Flashback' in t for t in trans_actifs): action = 'shift'
                        elif any('Melting' in t for t in trans_actifs): action = 'drop'

                    # APPLICATION DES EFFETS
                    if action == 'drop' and last_p_frame is not None:
                        p_len = len(last_p_frame)
                        actual_data = last_p_frame + b'\x00' * (chunk_size - p_len) if p_len <= chunk_size else last_p_frame[:chunk_size]
                        stats['i_drop'] += 1
                        # On ne l'ajoute pas à l'historique pour ne pas fausser la moyenne de poids
                        
                    elif action == 'shift' and last_i_frame is not None:
                        i_len = len(last_i_frame)
                        actual_data = last_i_frame + b'\x00' * (chunk_size - i_len) if i_len <= chunk_size else last_i_frame[:chunk_size]
                        stats['i_shift'] += 1
                        
                    else:
                        if frame_type == 0:
                            last_i_frame = actual_data
                            
                        elif frame_type == 1:
                            p_events = [e for e in active_events if '[MOUVEMENT]' in e['type']]
                            
                            # Initialisation des buffers de mouvement
                            for ev in active_events:
                                if not ev['triggered']:
                                    ev['triggered'] = True
                                    if '[MOUVEMENT]' in ev['type']:
                                        base_frame = last_p_frame or actual_data
                                        if 'Smear' in ev['type']:
                                            ev['state']['data'] = base_frame
                                        else:
                                            buf = ev['buffer']
                                            cycle = history_buffer[-buf:] if len(history_buffer) >= buf else history_buffer.copy()
                                            if not cycle: cycle = [base_frame]
                                            
                                            if 'Reverse' in ev['type']: cycle.reverse()
                                            elif 'Shuffle' in ev['type']: random.shuffle(cycle)
                                            
                                            ev['state']['cycle'] = cycle
                                            ev['state']['idx'] = 0

                            # Application de la manipulation de mouvement
                            if p_events:
                                current_ev = p_events[-1]
                                t = current_ev['type']
                                st = current_ev['state']
                                
                                if 'Smear' in t and 'data' in st: inject = st['data']
                                elif 'Wobble' in t and 'cycle' in st: inject = random.choice(st['cycle'])
                                elif 'cycle' in st:
                                    inject = st['cycle'][st['idx'] % len(st['cycle'])]
                                    st['idx'] += 1
                                else: inject = actual_data
                                    
                                p_len = len(inject)
                                actual_data = inject + b'\x00' * (chunk_size - p_len) if p_len <= chunk_size else inject[:chunk_size]
                                stats['generated'] += 1
                            else:
                                # Frame saine conservée
                                last_p_frame = actual_data
                                history_buffer.append(actual_data)
                                if len(history_buffer) > 20: history_buffer.pop(0)

                chunk_data = actual_data + pad_bytes
            
            f_out.write(header)
            f_out.write(chunk_data)
            
    log_cb(f"   Coupes détruites (Melting) : {stats['i_drop']}")
    log_cb(f"   Coupes décalées (Flashback) : {stats['i_shift']}")
    log_cb(f"   Frames mouvement glitchées : {stats['generated']}")


def process_video(inp, out, gop_val, timeline_events, log_cb, done_cb):
    temp_avi = "temp_raw.avi"
    moshed_avi = "temp_moshed.avi"
    moshed_no_audio = "temp_final.mp4"

    try:
        log_cb("Préparation de la timeline...")
        run_cmd([
            "ffmpeg", "-y", "-i", inp,
            "-r", "25", "-c:v", "mpeg4", "-q:v", "2",
            "-g", str(gop_val), "-bf", "0",
            "-sc_threshold", "40",  # <--- Force la détection des scènes
            "-an", temp_avi
        ], "Extraction vidéo (25 FPS constant)", log_cb)

        mosh_avi(temp_avi, moshed_avi, timeline_events, log_cb)

        run_cmd([
            "ffmpeg", "-y", "-i", moshed_avi,
            "-c:v", "libx264", "-crf", "18",
            "-pix_fmt", "yuv420p",
            moshed_no_audio
        ], "Cuisson de l'image (H.264)", log_cb)

        audio_filters = []
        for ev in timeline_events:
            if ev['audio']:
                s, e, t = ev['start'], ev['end'], ev['type']
                if 'Smear' in t: audio_filters.append(f"vibrato=f=10:d=1:enable='between(t,{s},{e})'")
                elif 'Stutter' in t or 'Shuffle' in t: audio_filters.append(f"tremolo=f=20:d=1:enable='between(t,{s},{e})'")
                elif 'Wobble' in t: audio_filters.append(f"flanger=delay=15:depth=10:enable='between(t,{s},{e})'")
                elif 'Melting' in t: audio_filters.append(f"aecho=0.8:0.9:100:0.5:enable='between(t,{s},{e})'")
                elif 'Flashback' in t: audio_filters.append(f"aphaser=type=t:speed=2:decay=0.6:enable='between(t,{s},{e})'")

        has_audio = False
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", inp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if probe.stdout.strip(): has_audio = True

        if audio_filters and has_audio:
            af_string = ",".join(audio_filters)
            log_cb(f"-> Application de {len(audio_filters)} corruptions audio synchronisées...")
            cmd_audio = [
                "ffmpeg", "-y", 
                "-i", moshed_no_audio, "-i", inp, 
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", 
                "-af", af_string,
                "-map", "0:v:0", "-map", "1:a:0?", "-shortest", out
            ]
        elif has_audio:
            log_cb("-> Mixage audio standard (sans filtres de corruption)...")
            cmd_audio = [
                "ffmpeg", "-y", 
                "-i", moshed_no_audio, "-i", inp, 
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", 
                "-map", "0:v:0", "-map", "1:a:0?", "-shortest", out
            ]
        else:
            log_cb("-> Aucune piste audio détectée. Export vidéo seul.")
            cmd_audio = [
                "ffmpeg", "-y", 
                "-i", moshed_no_audio, 
                "-c:v", "copy", out
            ]

        run_cmd(cmd_audio, "Mixage audio final", log_cb)
        log_cb(f"\n[SUCCESS] Rendu terminé ! Fichier dispo : {out}")

    except Exception as e:
        log_cb(f"\n[!] Arrêt du processus. Erreur: {e}")
    finally:
        for f in [temp_avi, moshed_avi, moshed_no_audio]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        done_cb()