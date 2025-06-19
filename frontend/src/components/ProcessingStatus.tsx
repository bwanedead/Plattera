import React from 'react'

const ProcessingStatus: React.FC = () => {
  return (
    <div className="processing-status">
      <div className="spinner"></div>
      <p>Processing legal description...</p>
      <small>This may take a moment while we parse the text</small>
    </div>
  )
}

export default ProcessingStatus 