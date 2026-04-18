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
  const [volume, setVolume] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  
  const videoNode = useRef(null);
  const player = useRef(null);

  // Inicializar Video.js
  useEffect(() => {
    if (videoNode.current) {
      player.current = videojs(videoNode.current, {
        autoplay: false,
        controls: false,
        responsive: true,
        fluid: true,
        preload: 'auto',
        liveui: true,
        sources: [{
          src: STREAM_URL,
          // Se for HLS, use 'application/x-mpegURL'. Para MP3/AAC use 'audio/mpeg' ou deixe o videojs detectar
          type: STREAM_URL.includes('m3u8') ? 'application/x-mpegURL' : 'audio/mpeg'
        }]
      }, () => {
        console.log('Video.js Player pronto');
      });

      player.current.on('error', () => {
        const error = player.current.error();
        console.error('Erro Video.js:', error);
        setErrorMessage(`Erro: ${error.message}`);
        setIsPlaying(false);
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

  const togglePlay = () => {
    setErrorMessage('');
    if (!player.current) return;

    if (isPlaying) {
      player.current.pause();
      setIsPlaying(false);
    } else {
      // Para HLS, às vezes é melhor não recarregar o src toda vez se o player já estiver ok
      // mas se houver erro prévio, recarregamos.
      if (player.current.error()) {
        player.current.src({ 
          src: STREAM_URL, 
          type: 'application/x-mpegURL' 
        });
      }
      
      const playPromise = player.current.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            setIsPlaying(true);
            console.log("Reprodução HLS iniciada com sucesso");
          })
          .catch(error => {
            if (error.name !== 'AbortError') {
              console.error("Erro ao reproduzir:", error);
              setIsPlaying(false);
              setErrorMessage("O navegador bloqueou o áudio ou o stream está inacessível.");
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
                {isPlaying ? 'Ao Vivo Agora' : 'Sintonize'}
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
            className="w-24 h-24 bg-red-600 hover:bg-red-500 active:scale-95 text-white rounded-full flex items-center justify-center shadow-[0_0_50px_-12px_rgba(220,38,38,0.5)] transition-all duration-300"
          >
            {isPlaying ? (
              <Pause fill="currentColor" size={36} />
            ) : (
              <Play fill="currentColor" size={36} className="ml-1" />
            )}
          </button>

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

        <div className="mt-10 flex gap-6 text-neutral-500">
          <a href="#" className="hover:text-red-500 transition-colors"><Globe size={18} /></a>
          <a href="#" className="hover:text-red-500 transition-colors"><MessageCircle size={18} /></a>
          <a href="#" className="hover:text-red-500 transition-colors"><Share2 size={18} /></a>
          <a href="#" className="hover:text-red-500 transition-colors"><ExternalLink size={18} /></a>
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
