import React, { useState } from 'react'

interface TextInputFormProps {
  onSubmit: (text: string) => void
  disabled?: boolean
}

const TextInputForm: React.FC<TextInputFormProps> = ({ onSubmit, disabled = false }) => {
  const [text, setText] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (text.trim()) {
      onSubmit(text.trim())
    }
  }

  return (
    <form onSubmit={handleSubmit} className="text-input-form">
      <div className="form-group">
        <label htmlFor="legal-text">Legal Property Description:</label>
        <textarea
          id="legal-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste your legal property description here..."
          rows={10}
          disabled={disabled}
          required
        />
      </div>
      <button type="submit" disabled={disabled || !text.trim()}>
        Process Description
      </button>
    </form>
  )
}

export default TextInputForm 