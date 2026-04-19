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
  const [activeServer, setActiveServer] = useState('link02'); // link01 ou link02
  const [logs, setLogs] = useState([]);

  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [`[${time}] ${msg}`, ...prev].slice(0, 10));
  };
  
  const videoNode = useRef(null);
  const player = useRef(null);

  const getStreamUrl = (server) => `/stream/playlist.m3u8?server=${server}`;

  // Inicialização do Video.js
  useEffect(() => {
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
          src: getStreamUrl(activeServer),
          type: 'application/x-mpegURL'
        }]
      });

      player.current.on('error', () => {
        const error = player.current.error();
        addLog(`Erro no Servidor ${activeServer === 'link01' ? '01' : '02'}`);
        
        const nextServer = activeServer === 'link01' ? 'link02' : 'link01';
        
        fetch(getStreamUrl(activeServer))
          .then(res => {
            if (!res.ok && activeServer !== nextServer) {
              addLog(`Tentando Servidor Reserva...`);
              setActiveServer(nextServer);
            }
            return res.ok ? null : res.text();
          })
          .then(backendMsg => {
            if (backendMsg) setErrorMessage(backendMsg);
          })
          .catch(() => {
            if (activeServer !== nextServer) setActiveServer(nextServer);
          })
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
    }

    return () => {
      if (player.current) {
        player.current.dispose();
      }
    };
  }, []);

  // Sincronizar volume
  useEffect(() => {
    if (player.current) {
      player.current.volume(isMuted ? 0 : volume);
    }
  }, [volume, isMuted]);

  const switchServer = (server) => {
    if (activeServer === server && isPlaying) return;
    
    addLog(`Trocando para ${server === 'link01' ? 'Servidor 01' : 'Servidor 02'}`);
    setActiveServer(server);
    setErrorMessage('');
    setIsLoading(true);

    if (player.current) {
      player.current.pause();
      player.current.src({ 
        src: getStreamUrl(server),
        type: 'application/x-mpegURL'
      });
      
      const playPromise = player.current.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            setIsPlaying(true);
            addLog("Tocando via nova fonte");
          })
          .catch(error => {
            setIsLoading(false);
            if (error.name !== 'AbortError') {
              addLog(`Erro na troca: ${error.message}`);
              setErrorMessage("Falha ao carregar este servidor.");
            }
          });
      }
    }
  };

  const togglePlay = () => {
    setErrorMessage('');
    addLog(`Iniciando via Servidor ${activeServer === 'link01' ? '01' : '02'}`);
    
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
        src: getStreamUrl(activeServer)
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
            {errorMessage && (
              <p className="mt-2 text-[10px] text-red-500 font-medium bg-red-500/10 px-3 py-1 rounded-full border border-red-500/20">
                {errorMessage}
              </p>
            )}
          </div>
        </div>

        <div className="w-full flex flex-col items-center gap-8">
          <button 
            onClick={togglePlay}
            disabled={isLoading}
            className={`group relative w-24 h-24 rounded-full flex items-center justify-center transition-all duration-500 ${
              isPlaying 
                ? 'bg-neutral-800 text-white hover:bg-neutral-700 shadow-[0_0_30px_rgba(0,0,0,0.3)]' 
                : 'bg-red-600 text-white hover:bg-red-500 hover:scale-105 shadow-[0_0_50px_rgba(220,38,38,0.3)]'
            } ${isLoading ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
          >
            {isLoading ? (
              <div className="w-8 h-8 border-4 border-white/20 border-t-white rounded-full animate-spin"></div>
            ) : isPlaying ? (
              <Pause className="w-10 h-10 fill-current" />
            ) : (
              <Play className="w-10 h-10 fill-current translate-x-1" />
            )}
          </button>

          <div className="flex flex-col items-center gap-4 animate-in fade-in zoom-in duration-500 mt-2">
            <div className="flex gap-2">
              <button 
                onClick={() => switchServer('link01')}
                className={`flex items-center gap-2 px-4 py-2 border rounded-full text-[9px] font-bold uppercase tracking-widest transition-all ${
                  activeServer === 'link01' 
                    ? 'bg-red-500/20 border-red-500/40 text-red-500' 
                    : 'bg-white/5 border-white/5 text-neutral-400 hover:bg-white/10 hover:text-white'
                }`}
              >
                <Radio size={12} />
                Link 01
              </button>
              <button 
                onClick={() => switchServer('link02')}
                className={`flex items-center gap-2 px-4 py-2 border rounded-full text-[9px] font-bold uppercase tracking-widest transition-all ${
                  activeServer === 'link02' 
                    ? 'bg-red-500/20 border-red-500/40 text-red-500' 
                    : 'bg-white/5 border-white/5 text-neutral-400 hover:bg-white/10 hover:text-white'
                }`}
              >
                <Radio size={12} />
                Link 02
              </button>
            </div>
            <p className="text-[8px] text-neutral-600 uppercase tracking-widest font-medium">
              Escolha uma fonte se houver falha
            </p>
            {errorMessage && (
              <p className="text-[9px] text-red-500/80 text-center max-w-[220px] leading-relaxed italic bg-red-500/5 px-4 py-2 rounded-lg border border-red-500/10">
                O player principal falhou. Tente o outro link acima.
              </p>
            )}
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
