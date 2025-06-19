import React from 'react'
import { Link } from 'react-router-dom'

const Header: React.FC = () => {
  return (
    <header className="header">
      <div className="container">
        <h1 className="logo">
          <Link to="/">Plattera</Link>
        </h1>
        <nav>
          <Link to="/" className="nav-link">Home</Link>
          <Link to="/process" className="nav-link">Process</Link>
          <Link to="/viewer" className="nav-link">Viewer</Link>
        </nav>
      </div>
    </header>
  )
}

export default Header 