import React from 'react';

export const ProductCard = ({
    title,
    description,
    href,
    image = null,
    gradient = "from-teal-500 to-cyan-500",
    badge = null
}) => {
    const CardWrapper = href ? 'a' : 'div';

    return (
        <CardWrapper
            href={href}
            className="product-card"
            style={{ textDecoration: 'none' }}
        >
            <div className={`product-card-image bg-gradient-to-br ${gradient}`}>
                {image && <img src={image} alt={title} />}
                {!image && (
                    <div className="product-card-pattern">
                        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
                            <circle cx="20" cy="30" r="8" fill="rgba(255,255,255,0.2)" />
                            <circle cx="70" cy="20" r="12" fill="rgba(255,255,255,0.15)" />
                            <circle cx="50" cy="60" r="6" fill="rgba(255,255,255,0.25)" />
                            <circle cx="80" cy="70" r="10" fill="rgba(255,255,255,0.1)" />
                        </svg>
                    </div>
                )}
                {badge && <span className="product-card-badge">{badge}</span>}
            </div>
            <div className="product-card-content">
                <h3 className="product-card-title">{title}</h3>
                <p className="product-card-description">{description}</p>
            </div>
            <style jsx>{`
        .product-card {
          display: block;
          background: white;
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
          transition: all 0.2s ease;
          border: 1px solid #e5e7eb;
        }
        .product-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 12px 24px rgba(0,0,0,0.1);
        }
        .product-card-image {
          height: 140px;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .product-card-image img {
          max-width: 80%;
          max-height: 80%;
          object-fit: contain;
        }
        .product-card-pattern {
          position: absolute;
          inset: 0;
        }
        .product-card-pattern svg {
          width: 100%;
          height: 100%;
        }
        .product-card-badge {
          position: absolute;
          top: 12px;
          right: 12px;
          padding: 4px 10px;
          background: rgba(0,0,0,0.6);
          color: white;
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          border-radius: 4px;
        }
        .product-card-content {
          padding: 20px;
        }
        .product-card-title {
          font-size: 18px;
          font-weight: 600;
          color: #111827;
          margin: 0 0 8px 0;
        }
        .product-card-description {
          font-size: 14px;
          color: #6b7280;
          margin: 0;
          line-height: 1.5;
        }
        :global(.dark) .product-card {
          background: #1f2937;
          border-color: #374151;
        }
        :global(.dark) .product-card-title {
          color: #f9fafb;
        }
        :global(.dark) .product-card-description {
          color: #9ca3af;
        }
      `}</style>
        </CardWrapper>
    );
};

export const ProductCardGrid = ({ children, cols = 3 }) => {
    return (
        <div className="product-grid">
            {children}
            <style jsx>{`
        .product-grid {
          display: grid;
          grid-template-columns: repeat(${cols}, 1fr);
          gap: 24px;
          margin: 32px 0;
        }
        @media (max-width: 900px) {
          .product-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
        @media (max-width: 600px) {
          .product-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
        </div>
    );
};

export default ProductCard;
