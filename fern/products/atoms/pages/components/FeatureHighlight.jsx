import React from 'react';

export const FeatureHighlight = ({
    title,
    features = [],
    badge = null,
    gradient = "from-teal-600 to-cyan-600"
}) => {
    return (
        <div className={`feature-highlight bg-gradient-to-br ${gradient}`}>
            <div className="feature-highlight-content">
                {badge && <span className="feature-badge">{badge}</span>}
                <h3 className="feature-title">{title}</h3>
                <ul className="feature-list">
                    {features.map((feature, index) => (
                        <li key={index} className="feature-item">
                            <span className="feature-check">✓</span>
                            {feature}
                        </li>
                    ))}
                </ul>
            </div>
            <style jsx>{`
        .feature-highlight {
          padding: 32px;
          border-radius: 16px;
          color: white;
          margin: 24px 0;
        }
        .feature-highlight-content {
          max-width: 600px;
        }
        .feature-badge {
          display: inline-block;
          padding: 4px 12px;
          background: rgba(255,255,255,0.2);
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          border-radius: 4px;
          margin-bottom: 16px;
        }
        .feature-title {
          font-size: 28px;
          font-weight: 700;
          margin: 0 0 20px 0;
        }
        .feature-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .feature-item {
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 16px;
          opacity: 0.95;
        }
        .feature-check {
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255,255,255,0.2);
          border-radius: 50%;
          font-size: 12px;
        }
      `}</style>
        </div>
    );
};

export default FeatureHighlight;
