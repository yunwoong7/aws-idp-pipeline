"use client";

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';
import React from 'react';
import Image from 'next/image';
import { cn } from '@/lib/utils';
import { SecureImage } from '@/components/ui/secure-image';


// Import highlight.js styles
import 'highlight.js/styles/github-dark.css';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  onDocumentClick?: (documentPath: string, filename?: string) => void;
  indexId?: string;
}

export function MarkdownRenderer({ content, className = "", onDocumentClick, indexId }: MarkdownRendererProps) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const copyToClipboard = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch (err) {
      console.error('클립보드 복사 실패:', err);
    }
  };

  return (
    <div className={cn(
      "w-full max-w-none break-words overflow-wrap-anywhere",
      "prose prose-sm max-w-none",
      "prose-headings:text-white prose-p:text-white/90",
      "prose-strong:text-white prose-em:text-gray-300",
      "prose-code:text-blue-300 prose-code:bg-gray-800/80",
      "prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-700",
      "prose-blockquote:border-l-blue-500 prose-blockquote:text-gray-300",
      "prose-ul:text-white/90 prose-ol:text-white/90 prose-li:text-white/90",
      "prose-table:border-gray-600 prose-th:text-white prose-td:text-white/90",
      "prose-hr:border-gray-600",
      "prose-a:text-blue-400 prose-a:hover:text-blue-300",
      "markdown-content",
      className
    )}>
      <style jsx>{`
        /* prose 클래스가 기본 리스트 스타일을 처리하므로 최소한의 조정만 적용 */
        .markdown-content ul ul,
        .markdown-content ol ol,
        .markdown-content ul ol,
        .markdown-content ol ul {
          margin-top: 0.5rem;
          margin-bottom: 0.5rem;
        }
        
        .markdown-content li {
          margin: 0.25rem 0;
        }
        
        /* 마커 색상 조정 */
        .markdown-content ul li::marker,
        .markdown-content ol li::marker {
          color: rgba(255, 255, 255, 0.7);
        }
        
        .markdown-content {
          line-height: 1.6;
          word-break: break-word;
          overflow-wrap: anywhere;
          max-width: 100%;
          overflow: hidden;
        }
        
        .markdown-content > *:first-child {
          margin-top: 0 !important;
        }
        
        .markdown-content > *:last-child {
          margin-bottom: 0 !important;
        }
        
        /* 모든 요소의 기본 여백 정규화 */
        .markdown-content p {
          margin-top: 0;
          margin-bottom: 1rem;
          line-height: 1.7;
        }

        .markdown-content p:last-child {
          margin-bottom: 0;
        }

        /* br 태그 줄바꿈 보장 */
        .markdown-content br {
          display: block;
          content: "";
          margin-top: 0.5rem;
        }

        /* 리스트 여백 조정 */
        .markdown-content ol,
        .markdown-content ul {
          margin-top: 0.75rem;
          margin-bottom: 0.75rem;
          padding-left: 1.5rem;
        }

        .markdown-content ol:first-child,
        .markdown-content ul:first-child {
          margin-top: 0;
        }

        .markdown-content ol:last-child,
        .markdown-content ul:last-child {
          margin-bottom: 0;
        }

        /* 리스트 아이템 내부 단락 처리 */
        .markdown-content li > p {
          margin: 0;
          display: inline;
        }

        .markdown-content li > p:only-child {
          margin: 0;
        }

        /* 리스트 아이템 내부의 중첩 리스트 처리 */
        .markdown-content li > ul,
        .markdown-content li > ol {
          margin-top: 0.5rem;
          margin-bottom: 0;
        }

        /* 제목과 단락 사이 간격 */
        .markdown-content h1,
        .markdown-content h2,
        .markdown-content h3,
        .markdown-content h4,
        .markdown-content h5,
        .markdown-content h6 {
          margin-top: 1.5rem;
          margin-bottom: 0.75rem;
          line-height: 1.3;
        }

        .markdown-content h1:first-child,
        .markdown-content h2:first-child,
        .markdown-content h3:first-child {
          margin-top: 0;
        }

        /* 연속된 제목 처리 */
        .markdown-content h1 + h2,
        .markdown-content h2 + h3,
        .markdown-content h3 + h4 {
          margin-top: 0.5rem;
        }
        
        /* 문서 링크 스타일 오버라이드 */
        .markdown-content a[role="button"] {
          color: inherit !important;
          text-decoration: none !important;
          border: none !important;
          outline: none !important;
        }
        
        .markdown-content a[role="button"]:hover {
          color: inherit !important;
          text-decoration: none !important;
        }
        
        .markdown-content a[role="button"]:visited {
          color: inherit !important;
        }
        
        .markdown-content a[role="button"]:focus {
          outline: none !important;
        }
      `}</style>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // 코드 블록 처리 - rehype-highlight 사용
          pre({ children, ...props }: any) {
            const preElement = children?.props;
            const codeString = preElement?.children?.[0] || '';
            const className = preElement?.className || '';
            const match = /language-(\w+)/.exec(className);
            const language = match ? match[1] : '';

            return (
              <div className="relative group my-6 shadow-lg rounded-lg overflow-hidden border border-gray-700">
                <div className="flex items-center justify-between bg-gray-800/90 px-4 py-3 border-b border-gray-600">
                  <span className="text-sm font-medium text-gray-300 uppercase tracking-wide">
                    {language || 'code'}
                  </span>
                  <button
                    onClick={() => copyToClipboard(String(codeString))}
                    className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors px-3 py-1 rounded-md hover:bg-gray-700/50"
                  >
                    {copiedCode === String(codeString) ? (
                      <>
                        <Check className="h-4 w-4" />
                        <span>복사됨</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4" />
                        <span>복사</span>
                      </>
                    )}
                  </button>
                </div>
                <pre className="!mt-0 !rounded-none text-sm p-4 bg-gray-900 overflow-x-auto" {...props}>
                  {children}
                </pre>
              </div>
            );
          },
          // 인라인 코드 처리
          code({ node, inline, className, children, ...props }: any) {
            if (inline) {
              return (
                <code className="bg-gray-800/80 px-2 py-1 rounded-md text-sm font-mono text-blue-300 border border-gray-600/50" {...props}>
                  {children}
                </code>
              );
            }
            return <code {...props}>{children}</code>;
          },
          // 링크 처리
          a({ href, children, ...props }) {
            console.log('MarkdownRenderer - Link detected:', { href, children });
            
            // 문서 링크 처리
            if (href?.startsWith('document://')) {
              const documentPath = href.replace('document://', '');
              
              const handleDocumentClick = (e: React.MouseEvent) => {
                e.preventDefault();
                e.stopPropagation();
                
                console.log('Document button clicked:', {
                  href,
                  documentPath,
                  children
                });
                
                // onDocumentClick prop이 있으면 사용자 정의 핸들러 호출
                if (onDocumentClick) {
                  const filename = Array.isArray(children) ? children.join('') : String(children);
                  onDocumentClick(documentPath, filename);
                  return;
                }
                
                // 기본 동작: pre-signed URL로 직접 열기
                if (documentPath.startsWith('https://')) {
                  console.log('Opening pre-signed URL directly:', documentPath);
                  window.open(documentPath, '_blank');
                  return;
                }
                
                // Fallback: show alert if URL is not valid
                console.log('Invalid document URL:', documentPath);
                alert('유효하지 않은 문서 URL입니다: ' + documentPath);
              };
              
              // a 태그를 사용하되 href를 제거하고 링크 동작을 무력화
              return (
                <a
                  {...(props as any)}
                  href={null as any}
                  onClick={handleDocumentClick}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleDocumentClick(e as any);
                    }
                  }}
                  onMouseDown={(e) => e.preventDefault()}
                  onContextMenu={(e) => e.preventDefault()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-500/20 to-purple-500/20 hover:from-blue-500/30 hover:to-purple-500/30 text-blue-300 hover:text-blue-100 border border-blue-500/50 hover:border-blue-400/70 rounded-md text-sm font-medium transition-all duration-300 cursor-pointer mx-0.5 shadow-sm hover:shadow-md hover:shadow-blue-500/25 transform hover:scale-[1.02] active:scale-[0.98] no-underline"
                  title="PDF 문서 보기"
                  style={{ textDecoration: 'none', color: 'inherit' }}
                  role="button"
                  tabIndex={0}
                >
                  <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="truncate max-w-[200px]">{children}</span>
                  <svg className="w-3 h-3 flex-shrink-0 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              );
            }
            
            // 일반 링크 처리
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 underline"
                {...(props as any)}
              >
                {children}
              </a>
            );
          },
          // 이미지 처리
          img({ src, alt, ...props }) {
            if (!src || typeof src !== 'string') return null;
            
            // S3 URI 또는 HTTP/HTTPS URL 확인
            if (src.startsWith('s3://')) {
              return (
                <SecureImage
                  s3Uri={src}
                  projectId={indexId || ''}
                  alt={alt || '이미지'}
                  className="max-w-full h-auto rounded-lg border border-gray-600 my-4"
                />
              );
            }
            
            // 일반 이미지는 Next.js Image 컴포넌트 사용
            return (
              <Image
                src={src}
                alt={alt || 'image'}
                width={800}
                height={600}
                className="max-w-full h-auto rounded-lg border border-gray-600 my-4"
                unoptimized
              />
            );
          },
          // 제목 처리 - prose 클래스와 함께 사용
          h1({ children, ...props }) {
            return (
              <h1 className="text-2xl font-bold text-white mb-4 mt-6" {...(props as any)}>
                {children}
              </h1>
            );
          },
          h2({ children, ...props }) {
            return (
              <h2 className="text-xl font-bold text-white mb-3 mt-5" {...(props as any)}>
                {children}
              </h2>
            );
          },
          h3({ children, ...props }) {
            return (
              <h3 className="text-lg font-bold text-white mb-2 mt-4" {...(props as any)}>
                {children}
              </h3>
            );
          },
          // 리스트 처리
          ul({ children, ...props }) {
            return (
              <ul className="list-disc list-inside space-y-1 text-white/90 my-2 ml-4 text-base font-medium" {...(props as any)}>
                {children}
              </ul>
            );
          },
          ol({ children, ...props }) {
            return (
              <ol className="list-decimal list-inside space-y-1 text-white/90 my-2 ml-4 text-base font-medium" {...(props as any)}>
                {children}
              </ol>
            );
          },
          li({ children, ...props }) {
            return (
              <li className="text-white/90 leading-relaxed break-words overflow-wrap-anywhere text-base font-medium [&>p]:inline [&>p]:m-0" {...(props as any)}>
                {children}
              </li>
            );
          },
          // 표 처리
          table({ children, ...props }) {
            return (
              <div className="overflow-x-auto my-6 rounded-lg border border-gray-600 bg-gray-900/50">
                <table className="min-w-full" {...(props as any)}>
                  {children}
                </table>
              </div>
            );
          },
          thead({ children, ...props }) {
            return (
              <thead className="bg-gray-800/70" {...(props as any)}>
                {children}
              </thead>
            );
          },
          th({ children, ...props }) {
            return (
              <th className="px-4 py-3 text-left text-white font-semibold border-b border-gray-600 first:rounded-tl-lg last:rounded-tr-lg" {...(props as any)}>
                {children}
              </th>
            );
          },
          td({ children, ...props }) {
            return (
              <td className="px-4 py-3 text-white/90 border-b border-gray-700 last:border-b-0" {...(props as any)}>
                {children}
              </td>
            );
          },
          // 인용문 처리
          blockquote({ children, ...props }) {
            return (
              <blockquote className="border-l-4 border-blue-500 pl-6 pr-4 py-4 my-6 bg-gray-800/50 rounded-r-lg shadow-lg" {...(props as any)}>
                <div className="text-gray-300 italic text-sm leading-relaxed">
                  {children}
                </div>
              </blockquote>
            );
          },
          // 구분선 처리
          hr({ ...props }) {
            return (
              <hr className="border-gray-600 my-6" {...(props as any)} />
            );
          },
          // 강조 처리
          strong({ children, ...props }) {
            return (
              <strong className="font-bold text-white" {...(props as any)}>
                {children}
              </strong>
            );
          },
          em({ children, ...props }) {
            return (
              <em className="italic text-gray-300" {...(props as any)}>
                {children}
              </em>
            );
          },
          // 단락 처리 - prose 스타일과 조화
          p({ children, ...props }) {
            return (
              <p className="text-white/90 mb-4 leading-[1.7] break-words overflow-wrap-anywhere whitespace-pre-wrap" {...(props as any)}>
                {children}
              </p>
            );
          },
          // 줄바꿈 처리
          br({ ...props }) {
            return <br className="block my-2" {...(props as any)} />;
          }
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}