import React from 'react';

export const Hero = ({
    title = "Atoms Documentation",
    subtitle = "Build enterprise-grade voice AI agents in minutes",
    badge = null
}) => {
    return (
        <div className="hero-container">
            <div className="hero-wave-bg" />
            <div className="hero-content">
                {badge && <span className="hero-badge">{badge}</span>}
                <h1 className="hero-title">{title}</h1>
                <p className="hero-subtitle">{subtitle}</p>
            </div>
            <style jsx>{`
        .hero-container {
          position: relative;
          padding: 80px 20px 100px;
          text-align: center;
          overflow: hidden;
          margin: -24px -24px 40px -24px;
          border-radius: 0 0 24px 24px;
        }
        .hero-wave-bg {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, #0d9488 0%, #0891b2 50%, #0284c7 100%);
          opacity: 0.1;
          z-index: 0;
        }
        .hero-wave-bg::before {
          content: '';
          position: absolute;
          bottom: -50px;
          left: -10%;
          right: -10%;
          height: 200px;
          background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 320'%3E%3Cpath fill='%23217D80' fill-opacity='0.3' d='M0,96L48,112C96,128,192,160,288,165.3C384,171,480,149,576,154.7C672,160,768,192,864,197.3C960,203,1056,181,1152,154.7C1248,128,1344,96,1392,80L1440,64L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z'%3E%3C/path%3E%3C/svg%3E") no-repeat center;
          background-size: cover;
        }
        .hero-content {
          position: relative;
          z-index: 1;
        }
        .hero-badge {
          display: inline-block;
          padding: 6px 16px;
          background: linear-gradient(135deg, #217D80, #0891b2);
          color: white;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          border-radius: 20px;
          margin-bottom: 20px;
        }
        .hero-title {
          font-size: 48px;
          font-weight: 700;
          color: #111827;
          margin: 0 0 16px 0;
          letter-spacing: -1px;
        }
        .hero-subtitle {
          font-size: 20px;
          color: #6b7280;
          margin: 0;
          max-width: 600px;
          margin: 0 auto;
        }
        @media (max-width: 768px) {
          .hero-title {
            font-size: 32px;
          }
          .hero-subtitle {
            font-size: 16px;
          }
        }
        :global(.dark) .hero-title {
          color: #f9fafb;
        }
        :global(.dark) .hero-wave-bg {
          opacity: 0.2;
        }
      `}</style>
        </div>
    );
};

export default Hero;
