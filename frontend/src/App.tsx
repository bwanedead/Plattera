import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Header from './components/Header'
import HomePage from './pages/HomePage'
import ProcessPage from './pages/ProcessPage'
import ViewerPage from './pages/ViewerPage'
import './App.css'

function App() {
  return (
    <Router>
      <div className="App">
        <Header />
        <main>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/process" element={<ProcessPage />} />
            <Route path="/viewer" element={<ViewerPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App 