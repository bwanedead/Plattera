import React from 'react'
import Link from 'next/link'

const Header: React.FC = () => {
  return (
    <header className="header">
      <div className="container">
        <h1 className="logo">
          <Link href="/">Plattera</Link>
        </h1>
        <nav>
          <Link href="/" className="nav-link">Home</Link>
          <Link href="/process" className="nav-link">Process</Link>
          <Link href="/viewer" className="nav-link">Viewer</Link>
        </nav>
      </div>
    </header>
  )
}

export default Header 