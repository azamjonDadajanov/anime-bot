import React, { useState, useEffect } from 'react';

const OrientationWrapper = ({ children }) => {
  const [isPortrait, setIsPortrait] = useState(false);

  useEffect(() => {
    // Ekran orientatsiyasini tekshirish funksiyasi
    const checkOrientation = () => {
      // Oyna balandligi kengligidan katta bo'lsa - vertikal rejim
      if (window.innerHeight > window.innerWidth) {
        setIsPortrait(true);
      } else {
        setIsPortrait(false);
      }
    };

    // Dastlabki tekshiruv
    checkOrientation();

    // Ekran o'lchami yoki orientatsiyasi o'zgarganda ishlaydi
    window.addEventListener('resize', checkOrientation);
    window.addEventListener('orientationchange', checkOrientation);

    return () => {
      window.removeEventListener('resize', checkOrientation);
      window.removeEventListener('orientationchange', checkOrientation);
    };
  }, []);

  // Screen Orientation API orqali majburiy Fullscreen va Lock qilishga urinish (ixtiyoriy)
  const handleRequestLandscape = async () => {
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
      if (screen.orientation && screen.orientation.lock) {
        await screen.orientation.lock('landscape');
      }
    } catch (error) {
      console.log("Full-screen yoki orientation lock ruxsat berilmadi:", error);
    }
  };

  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden', position: 'relative' }}>
      {/* Vertikal rejim uchun ogohlantirish overlay'i */}
      {isPortrait && (
        <div style={styles.overlay}>
          <div style={styles.iconContainer}>
            <div style={styles.phoneIcon}>📱</div>
            <div style={styles.rotateArrow}>🔄</div>
          </div>
          <h2 style={styles.title}>Iltimos, telefoningizni burang</h2>
          <p style={styles.text}>
            O'yinni eng yaxshi tajriba bilan o'ynash uchun telefonni gorizontal (landscape) holatga o'tkazing.
          </p>
          <button style={styles.button} onClick={handleRequestLandscape}>
            To'liq ekranga o'tish
          </button>
        </div>
      )}

      {/* Asosiy o'yin (Three.js Canvas va boshqalar) */}
      <div style={{ width: '100%', height: '100%', visibility: isPortrait ? 'hidden' : 'visible' }}>
        {children}
      </div>
    </div>
  );
};

// Oddiy inline stillar
const styles = {
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: '#0f172a',
    color: '#ffffff',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 9999,
    textAlign: 'center',
    padding: '20px',
    boxSizing: 'border-box',
  },
  iconContainer: {
    fontSize: '48px',
    marginBottom: '20px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  title: {
    fontSize: '22px',
    margin: '0 0 10px 0',
    fontWeight: 'bold',
  },
  text: {
    fontSize: '14px',
    color: '#94a3b8',
    maxWidth: '300px',
    marginBottom: '20px',
    lineHeight: '1.5',
  },
  button: {
    padding: '10px 20px',
    fontSize: '14px',
    fontWeight: '600',
    backgroundColor: '#3b82f6',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
  },
};

export default OrientationWrapper;