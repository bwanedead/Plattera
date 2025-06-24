import React from 'react';
import Link from 'next/link';
import { ParcelTracerLoader } from '../components/ParcelTracerLoader';

const AnimationTesterPage: React.FC = () => {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: '#121212',
      color: 'white',
      padding: '2rem',
      fontFamily: 'sans-serif'
    }}>
      <Link href="/" legacyBehavior>
        <a style={{ 
          position: 'absolute', 
          top: '2rem', 
          left: '2rem', 
          color: 'var(--accent-primary)',
          textDecoration: 'none'
        }}>
          &larr; Back to Home
        </a>
      </Link>
      <h1>Animation Tester</h1>
      <p style={{ color: '#aaa', marginTop: '0.5rem' }}>Component: <strong>ParcelTracerLoader</strong></p>
      <div style={{
        width: '300px',
        height: '300px',
        marginTop: '2rem',
        backgroundColor: '#1a1a1a',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid #333'
      }}>
        <ParcelTracerLoader />
      </div>
    </div>
  );
};

export default AnimationTesterPage; 