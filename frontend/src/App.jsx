import React, { useState, useRef, useEffect } from 'react';
import { Play, Pause, Volume2, VolumeX, Radio, ExternalLink, Globe, MessageCircle, Share2 } from 'lucide-react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

// Tente usar o link HLS se o .mp3 não funcionar. Geralmente é algo como:
// const STREAM_URL = 'http://172.16.224.75:80/stream1/index.m3u8'; 
// const STREAM_URL = 'http://172.16.224.75:8235/hls/hd-live0.m3u8'; 
// const STREAM_URL = 'http://45.224.108.178:8235/hls/hd-live0.m3u8';

// O STREAM_URL agora aponta para o nosso próprio backend, que age como um proxy.
// Isso resolve o problema de "Mixed Content" (tocar HTTP dentro de um site HTTPS)
// e também contorna problemas de CORS e bloqueios de porta em alguns navegadores.
const STREAM_URL = '/stream/playlist.m3u8';

function App() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [logs, setLogs] = useState([]);
  const [activeListeners, setActiveListeners] = useState(null);

  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [`[${time}] ${msg}`, ...prev].slice(0, 10));
  };
  
  const videoNode = useRef(null);
  const player = useRef(null);
  const listenerIdRef = useRef(null);

  const getStreamUrl = () => '/stream/playlist.m3u8?server=link01';

  // Inicialização do Video.js
  useEffect(() => {
    const existingId = sessionStorage.getItem('vicfm_listener_id');
    const listenerId = existingId ?? (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`);
    sessionStorage.setItem('vicfm_listener_id', listenerId);
    listenerIdRef.current = listenerId;

    if (videoNode.current) {
      player.current = videojs(videoNode.current, {
        autoplay: false,
        controls: false,
        preload: 'auto',
        responsive: true,
        fluid: true,
        html5: {
          vhs: {
            overrideNative: true
          },
          nativeAudioTracks: false,
          nativeVideoTracks: false
        },
        sources: [{
          src: getStreamUrl(),
          type: 'application/x-mpegURL'
        }]
      });

      player.current.on('error', () => {
        const error = player.current.error();
        addLog(`Erro no stream: ${error?.message ?? 'desconhecido'}`);

        fetch(getStreamUrl())
          .then(res => {
            return res.ok ? null : res.text();
          })
          .then(backendMsg => {
            if (backendMsg) setErrorMessage(backendMsg);
          })
          .catch(() => {})
          .finally(() => {
            setIsPlaying(false);
            setIsLoading(false);
          });
      });

      player.current.on('waiting', () => {
        addLog('Aguardando buffer...');
        setIsLoading(true);
      });

      player.current.on('playing', () => {
        addLog('Tocando agora!');
        setErrorMessage('');
        setIsLoading(false);
        setIsPlaying(true);
      });

      player.current.on('loadstart', () => {
        setIsLoading(true);
        addLog('Iniciando carga...');
      });

      setIsLoading(true);
      const playPromise = player.current.play();
      if (playPromise !== undefined) {
        playPromise.catch(() => {
          setIsLoading(false);
          addLog('Toque em Link 01 para iniciar.');
        });
      }
    }

    return () => {
      if (player.current) {
        player.current.dispose();
      }
    };
  }, []);

  useEffect(() => {
    const updateCount = () => {
      fetch('/api/listeners')
        .then(res => (res.ok ? res.json() : null))
        .then(data => {
          if (data && typeof data.active === 'number') setActiveListeners(data.active);
        })
        .catch(() => {});
    };

    updateCount();
    const intervalId = setInterval(updateCount, 10000);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const listenerId = listenerIdRef.current;
    if (!listenerId) return;

    const ping = () =>
      fetch('/api/listeners/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: listenerId, playing: true }),
        keepalive: true
      })
        .then(res => (res.ok ? res.json() : null))
        .then(data => {
          if (data && typeof data.active === 'number') setActiveListeners(data.active);
        })
        .catch(() => {});

    const stop = () =>
      fetch('/api/listeners/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: listenerId }),
        keepalive: true
      })
        .then(res => (res.ok ? res.json() : null))
        .then(data => {
          if (data && typeof data.active === 'number') setActiveListeners(data.active);
        })
        .catch(() => {});

    if (!isPlaying) {
      stop();
      return;
    }

    ping();
    const intervalId = setInterval(ping, 15000);
    return () => {
      clearInterval(intervalId);
      stop();
    };
  }, [isPlaying]);

  useEffect(() => {
    if (!isPlaying) return;

    const ping = () =>
      fetch('/api/health', { cache: 'no-store', keepalive: true }).catch(() => {});

    ping();
    const intervalId = setInterval(ping, 240000);
    return () => clearInterval(intervalId);
  }, [isPlaying]);

  // Sincronizar volume
  useEffect(() => {
    if (player.current) {
      player.current.volume(isMuted ? 0 : volume);
    }
  }, [volume, isMuted]);

  const togglePlay = () => {
    setErrorMessage('');
    addLog('Iniciando via Link 01');
    
    if (!player.current) {
      setErrorMessage('Player não inicializado.');
      return;
    }

    if (isPlaying) {
      player.current.pause();
      setIsPlaying(false);
    } else {
      setIsLoading(true);
      
      if (player.current.error()) {
        player.current.error(null);
      }

      player.current.src({ 
        src: getStreamUrl()
      });
      
      const playPromise = player.current.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            addLog("Play com sucesso");
          })
          .catch(error => {
            setIsLoading(false);
            if (error.name !== 'AbortError') {
              addLog(`Erro: ${error.message}`);
              setErrorMessage("Falha ao iniciar áudio.");
            }
          });
      }
    }
  };

  const handleVolumeChange = (e) => {
    const newVolume = parseFloat(e.target.value);
    setVolume(newVolume);
    if (newVolume > 0) setIsMuted(false);
  };

  const toggleMute = () => {
    setIsMuted(!isMuted);
  };

  const getDisplayedListeners = () => {
    if (activeListeners === null) return null;

    const now = new Date();
    const hour = now.getHours();
    const day = now.getDay();
    const isWeekend = day === 0 || day === 6;
    const isMadrugada = hour >= 0 && hour < 6;

    const baseByHour = {
      8: 70,
      9: 72,
      10: 74,
      11: 76,
      14: 214,
      15: 216,
      16: 218,
      17: 220,
    };

    const base = isMadrugada ? 0 : (baseByHour[hour] ?? 0);
    const total = base + activeListeners;
    return isWeekend ? Math.floor(total / 2) : total;
  };

  const displayedListeners = getDisplayedListeners();

  return (
    <div className="min-h-screen bg-neutral-950 text-white flex flex-col items-center justify-center p-4 font-sans selection:bg-red-500/30">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] bg-red-900/10 blur-[120px] rounded-full"></div>
        <div className="absolute -bottom-[20%] -right-[10%] w-[50%] h-[50%] bg-red-900/5 blur-[120px] rounded-full"></div>
      </div>

      <div className="relative w-full max-w-md bg-neutral-900/40 backdrop-blur-xl border border-white/5 rounded-[2.5rem] shadow-2xl overflow-hidden p-8 flex flex-col items-center">
        
        <div className="w-48 h-48 bg-neutral-800/50 rounded-3xl flex items-center justify-center mb-8 shadow-inner border border-white/5 group overflow-hidden">
          <div className="relative w-full h-full flex flex-col items-center justify-center">
            <Radio className={`w-20 h-20 ${isPlaying ? 'text-red-500 animate-pulse' : 'text-neutral-600'} transition-colors duration-500`} />
            <span className="mt-4 text-xs font-bold tracking-[0.2em] text-neutral-500 uppercase">VICFM 91.5</span>
            <div className="absolute inset-0 bg-neutral-900/80 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-[10px] text-neutral-400 p-4 text-center">
              Espaço para Logo Oficial VICFM 91.5
            </div>
          </div>
        </div>

        <div className="text-center mb-10 w-full">
          <h1 className="text-2xl font-semibold tracking-tight mb-1">VICFM 91.5</h1>
          <div className="flex flex-col items-center justify-center gap-2">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isPlaying ? 'bg-red-500 animate-ping' : 'bg-neutral-600'}`}></span>
              <p className="text-sm text-neutral-400 font-medium uppercase tracking-widest">
                {isLoading ? 'Carregando...' : (isPlaying ? 'Ao Vivo Agora' : 'Sintonize')}
              </p>
            </div>
            <p className="text-[10px] text-neutral-500 font-medium">
              Carregamento pode levar alguns segundos
            </p>
            <p className="text-[10px] text-neutral-600 font-medium">
              {displayedListeners === null ? 'Ouvintes agora: —' : `Ouvintes agora: ${displayedListeners}`}
            </p>
            {errorMessage && (
              <p className="mt-2 text-[10px] text-red-500 font-medium bg-red-500/10 px-3 py-1 rounded-full border border-red-500/20">
                {errorMessage}
              </p>
            )}
          </div>
        </div>

        <div className="w-full flex flex-col items-center gap-8">
          <div className="flex flex-col items-center gap-4 animate-in fade-in zoom-in duration-500 mt-2">
            <div className="flex gap-2">
              <button 
                onClick={togglePlay}
                disabled={isLoading}
                className={`flex items-center justify-center gap-3 px-6 py-4 border rounded-full text-[11px] font-bold uppercase tracking-widest transition-all ${
                  isPlaying
                    ? 'bg-neutral-800 border-white/5 text-white hover:bg-neutral-700'
                    : 'bg-red-600 border-red-500/40 text-white hover:bg-red-500'
                } ${isLoading ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
              >
                {isLoading ? (
                  <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
                ) : isPlaying ? (
                  <Pause className="w-4 h-4 fill-current" />
                ) : (
                  <Play className="w-4 h-4 fill-current translate-x-0.5" />
                )}
                <Radio size={14} />
                Link 01
              </button>
            </div>
          </div>

          <div className="w-full flex items-center gap-4 px-4">
            <button onClick={toggleMute} className="text-neutral-400 hover:text-white transition-colors">
              {isMuted || volume === 0 ? <VolumeX size={20} /> : <Volume2 size={20} />}
            </button>
            <input 
              type="range" 
              min="0" 
              max="1" 
              step="0.01" 
              value={volume}
              onChange={handleVolumeChange}
              className="flex-1 h-1 bg-neutral-700 rounded-lg appearance-none cursor-pointer accent-red-500"
            />
          </div>
        </div>

        <div className="mt-10 flex flex-col items-center gap-6 w-full">
          <div className="flex gap-6 text-neutral-500">
            <a href="#" className="hover:text-red-500 transition-colors"><Globe size={18} /></a>
            <a href="#" className="hover:text-red-500 transition-colors"><MessageCircle size={18} /></a>
            <a href="#" className="hover:text-red-500 transition-colors"><Share2 size={18} /></a>
            <a href="#" className="hover:text-red-500 transition-colors"><ExternalLink size={18} /></a>
          </div>
          
          {logs.length > 0 && (
            <div className="w-full bg-black/20 rounded-xl p-3 border border-white/5 overflow-hidden">
              <p className="text-[8px] text-neutral-600 uppercase font-bold mb-2 tracking-widest">Logs de Sistema</p>
              <div className="max-h-24 overflow-y-auto space-y-1 flex flex-col-reverse">
                {logs.map((log, i) => (
                  <p key={i} className="text-[9px] font-mono text-neutral-500 border-l border-red-500/30 pl-2">
                    {log}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>

      </div>

      {/* Video.js Hidden Element */}
      <div data-vjs-player style={{ position: 'absolute', width: '1px', height: '1px', opacity: 0, pointerEvents: 'none' }}>
        <video ref={videoNode} className="video-js" playsInline />
      </div>

      <p className="mt-8 text-[10px] text-neutral-600 uppercase tracking-[0.3em]">
        Powered by VICFM Technology
      </p>
    </div>
  );
}

export default App;
