import React from 'react';

export const PathSelector = ({ paths }) => {
    return (
        <div className="path-selector">
            {paths.map((path, index) => (
                <a key={index} href={path.href} className="path-option">
                    <div className="path-icon">{path.icon}</div>
                    <div className="path-content">
                        <h3 className="path-title">{path.title}</h3>
                        <p className="path-description">{path.description}</p>
                    </div>
                    <div className="path-arrow">→</div>
                </a>
            ))}
            <style jsx>{`
        .path-selector {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin: 32px 0;
        }
        .path-option {
          display: flex;
          align-items: center;
          gap: 20px;
          padding: 24px;
          background: linear-gradient(135deg, rgba(33, 125, 128, 0.05), rgba(8, 145, 178, 0.05));
          border: 2px solid #e5e7eb;
          border-radius: 16px;
          text-decoration: none;
          transition: all 0.2s ease;
        }
        .path-option:hover {
          border-color: #217D80;
          transform: translateX(4px);
          box-shadow: 0 8px 24px rgba(33, 125, 128, 0.15);
        }
        .path-icon {
          width: 56px;
          height: 56px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #217D80, #0891b2);
          border-radius: 12px;
          font-size: 24px;
          flex-shrink: 0;
        }
        .path-content {
          flex: 1;
        }
        .path-title {
          font-size: 20px;
          font-weight: 600;
          color: #111827;
          margin: 0 0 4px 0;
        }
        .path-description {
          font-size: 14px;
          color: #6b7280;
          margin: 0;
        }
        .path-arrow {
          font-size: 24px;
          color: #217D80;
          font-weight: 300;
          opacity: 0;
          transition: opacity 0.2s ease;
        }
        .path-option:hover .path-arrow {
          opacity: 1;
        }
        :global(.dark) .path-option {
          background: linear-gradient(135deg, rgba(13, 148, 136, 0.1), rgba(8, 145, 178, 0.1));
          border-color: #374151;
        }
        :global(.dark) .path-title {
          color: #f9fafb;
        }
        :global(.dark) .path-description {
          color: #9ca3af;
        }
        @media (max-width: 600px) {
          .path-option {
            flex-direction: column;
            text-align: center;
          }
          .path-arrow {
            display: none;
          }
        }
      `}</style>
        </div>
    );
};

export default PathSelector;
