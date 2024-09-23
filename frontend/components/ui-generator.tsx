'use client'

import React, { useState, useEffect, useRef, useCallback, createElement } from 'react'
import { Button } from '@nlmk/ds-2.0'
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { SendIcon, ImageIcon, Maximize2, Download, Copy, Minimize2, Check, Settings } from 'lucide-react'
import Editor from 'react-simple-code-editor'
import { highlight, languages } from 'prismjs'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-jsx'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-tsx'
import 'prismjs/themes/prism-tomorrow.css'
import axios from 'axios';
import { Textarea } from "@/components/ui/textarea";
import * as NLMKDS from '@nlmk/ds-2.0'
import { PageEditor } from "./PageEditor";
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Sandpack } from "@codesandbox/sandpack-react";
import { getParameters } from 'codesandbox/lib/api/define';

interface Message {
  id: string
  text: string
  sender: 'user' | 'ai'
  image?: string
}

interface Version {
  id: string
  code: string
}

const DummyComponent = () => {
  return (
    <div>
      <h1>Dummy Component</h1>
      <p>This is a dummy component generated in admin mode.</p>
    </div>
  );
}

const UiGenerator = () => {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isGeneratingUI, setIsGeneratingUI] = useState(false)
  const [generatedCode, setGeneratedCode] = useState('')
  const [editableCode, setEditableCode] = useState('')
  const [showDesign, setShowDesign] = useState(false)
  const [versions, setVersions] = useState<Version[]>([])
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isAdminMode, setIsAdminMode] = useState(false)
  const [previewType, setPreviewType] = useState<'iframe' | 'codesandbox'>('codesandbox')
  const [currentVersion, setCurrentVersion] = useState(1)
  const [isCopied, setIsCopied] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    setMessages([{ id: '1', text: "Здравствуйте! Как я могу помочь вам сгенерировать дизайн интерфейса сегодня?", sender: 'ai' }])
  }, [])

  useEffect(() => {
    if (generatedCode) {
      const newVersion = {
        id: (versions.length + 1).toString(),
        code: generatedCode
      };
      setVersions(prev => [...prev, newVersion]);
      setSelectedVersion(newVersion.id);
      setCurrentVersion(versions.length + 1);
      setEditableCode(generatedCode);
      updateIndexFile(generatedCode);
    }
  }, [generatedCode])

  const updateIndexFile = useCallback(async (code: string) => {
    try {
      await axios.post('http://localhost:5000/update-preview', { code }, {
        headers: {
          'Content-Type': 'application/json',
        },
      });
      console.log('index.tsx updated successfully');
    } catch (error) {
      console.error('Error updating index.tsx:', error);
    }
  }, []);

  const handleSendAndGenerate = async () => {
    if (!input.trim()) {
      setMessages(prev => [...prev, { id: Date.now().toString(), text: "Пожалуйста, введите вопрос или описание для интерфейса.", sender: 'ai' }]);
      return;
    }

    const newUserMessage: Message = { id: Date.now().toString(), text: input, sender: 'user' }
    setMessages(prev => [...prev, newUserMessage])
    setInput('')

    setIsGeneratingUI(true);
    setMessages(prev => [...prev, { id: Date.now().toString(), text: "Генерция изайна интерфейса...", sender: 'ai' }]);
    
    if (isAdminMode) {
      setTimeout(() => {
        const dummyCode = `
const DummyComponent = () => {
  return (
    <div>
      <h1>Dummy Component</h1>
      <p>This is a dummy component generated in admin mode.</p>
    </div>
  );
}

export default DummyComponent;
        `;
        setGeneratedCode(dummyCode);
        setEditableCode(dummyCode);
        updateSandboxPreview(dummyCode);
        setShowDesign(true);
        setMessages(prev => [...prev, { id: Date.now().toString(), text: "Дизайн интерфейса успешно сгенерирован в режиме администратора!", sender: 'ai' }]);
        setIsGeneratingUI(false);
      }, 1000);
    } else {
      try {
        console.log('Sending request to backend...');
        const response = await axios.post('http://localhost:5000/generate', { question: input }, {
          headers: {
            'Content-Type': 'application/json',
          },
        });
        console.log('Received response from backend:', response.data);
        const generatedCode = response.data.result;
        console.log('Generated code:', generatedCode);

        if (typeof generatedCode === 'string' && generatedCode.startsWith('An error occurred')) {
          throw new Error(generatedCode);
        }

        // Modify the generated code to use placeholder components
        const modifiedGeneratedCode = generatedCode.replace(
          "import { Header, Button, Grid } from '@nlmk/ds-2.0';",
          "// Note: Using placeholder components. Replace with actual @nlmk/ds-2.0 components when available.\n" +
          "const Header = ({ children }) => <header>{children}</header>;\n" +
          "const Button = ({ children }) => <button>{children}</button>;\n" +
          "const Grid = ({ children }) => <div style={{ display: 'grid' }}>{children}</div>;"
        );

        setGeneratedCode(modifiedGeneratedCode);
        console.log('State updated with generated code');

        setEditableCode(modifiedGeneratedCode);
        console.log('Editable code updated');

        await updateIndexFile(modifiedGeneratedCode);

        setShowDesign(true);
        console.log('Show design set to true');

        setMessages(prev => [...prev, { id: Date.now().toString(), text: "Дизайн интерфейса успешно сгенерирован!", sender: 'ai' }]);
      } catch (error: unknown) {
        console.error('Error generating UI:', error);
        if (axios.isAxiosError(error)) {
          console.error('Axios error details:', error.response?.data);
        }
        const errorMessage = error instanceof Error ? error.message : 'Неизвестная ошибка';
        setMessages(prev => [...prev, { id: Date.now().toString(), text: `Произошла ошибка при генерации интерфейса: ${errorMessage}`, sender: 'ai' }]);
      } finally {
        setIsGeneratingUI(false);
      }
    }
  };

  const updateSandboxPreview = useCallback((code: string) => {
    setGeneratedCode(code);
  }, []);

  const handleCreateNewDesign = () => {
    setMessages([{ id: Date.now().toString(), text: "Здравствуйте! Как  могу помочь вам сгенерировть дизайн интерфейса сегодня?", sender: 'ai' }])
    setGeneratedCode('')
    setEditableCode('')
    setShowDesign(false)
    setVersions([])
    setSelectedVersion(null)
  }

  const handleOpenDesignHistory = () => {
    alert('Функция итории дизайнов не реализована в этой демо-версии.')
  }

  const handleCodeChange = useCallback((code: string) => {
    setEditableCode(code);
    updateIndexFile(code);
    updateSandboxPreview(code);
  }, [updateIndexFile, updateSandboxPreview]);

  const renderComponent = (Component: any): React.ReactNode => {
    if (typeof Component === 'function') {
      try {
        return <Component />;
      } catch (error) {
        console.error('Error rendering component:', error);
        return <div className="text-red-500">Error rendering component: {error instanceof Error ? error.message : 'Unknown error'}</div>;
      }
    }
    return Component;
  };

  const handleAddImage = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = (e) => {
        const newMessage: Message = {
          id: Date.now().toString(),
          text: "Изображение заружено",
          sender: 'user',
          image: e.target?.result as string
        }
        setMessages(prev => [...prev, newMessage])
      }
      reader.readAsDataURL(file)
    }
  }

  const handlePaste = (event: React.ClipboardEvent) => {
    const items = event.clipboardData.items
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const blob = items[i].getAsFile()
        if (blob) {
          const reader = new FileReader()
          reader.onload = (e) => {
            const newMessage: Message = {
              id: Date.now().toString(),
              text: "Изображение вставлено",
              sender: 'user',
              image: e.target?.result as string
            }
            setMessages(prev => [...prev, newMessage])
          }
          reader.readAsDataURL(blob)
        }
      }
    }
  }

  const handleDownloadCode = () => {
    const element = document.createElement("a");
    const file = new Blob([editableCode], {type: 'text/plain'});
    element.href = URL.createObjectURL(file);
    element.download = "generated-component.tsx";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  }

  const handleCopyCode = () => {
    navigator.clipboard.writeText(editableCode).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000); // Reset after 2 seconds
    }, (err) => {
      console.error('Не удалось скопировать текст: ', err);
    });
  }

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  }

  const getCodeSandboxFiles = useCallback(() => {
    // Modify the generated code to use placeholder components
    const modifiedGeneratedCode = generatedCode.replace(
      "import { Header, Button, Grid } from '@nlmk/ds-2.0';",
      "// Note: Using placeholder components. Replace with actual @nlmk/ds-2.0 components when available.\n" +
      "const Header = ({ children }) => <header>{children}</header>;\n" +
      "const Button = ({ children }) => <button>{children}</button>;\n" +
      "const Grid = ({ children }) => <div style={{ display: 'grid' }}>{children}</div>;"
    );

    return {
      "package.json": {
        content: JSON.stringify({
          dependencies: {
            "react": "^17.0.2",
            "react-dom": "^17.0.2",
          },
          main: "/src/index.js"
        })
      },
      "/src/App.js": {
        content: `
import React from "react";
${modifiedGeneratedCode}
        `.trim()
      },
      "/src/index.js": {
        content: `
import React from "react";
import ReactDOM from "react-dom";
import App from "./App";

ReactDOM.render(<App />, document.getElementById("root"));
        `.trim()
      },
      "/public/index.html": {
        content: `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>React App</title>
</head>
<body>
  <div id="root"></div>
</body>
</html>
        `.trim()
      }
    };
  }, [generatedCode]);

  const getCodeSandboxUrl = useCallback(() => {
    const parameters = getParameters({
      files: getCodeSandboxFiles() as Record<string, { content: string; isBinary?: boolean }>,
    });
    return `https://codesandbox.io/api/v1/sandboxes/define?parameters=${parameters}`;
  }, [getCodeSandboxFiles]);

  return (
    <div className="flex h-screen bg-[#EDEEEF]">
      <div className={`flex flex-col ${showDesign ? (isFullscreen ? 'w-0' : 'w-1/2') : 'w-full'} p-4 transition-all duration-300`}>
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center">
            <img src="logo_nlmk.svg" alt="NLMK Logo" className="h-12 mr-3" />
            <h1 className="text-2xl font-bold text-[#0053A0]">ИИ Генератор Интерфейса</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="relative">
              <Button
                variant="secondary"
                size="m"
                onClick={() => setShowSettings(!showSettings)}
                iconButton={<Settings className="h-4 w-4" />}
              />
              {showSettings && (
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-10">
                  <div className="flex items-center space-x-2 p-2">
                    <Switch
                      id="admin-mode"
                      checked={isAdminMode}
                      onCheckedChange={setIsAdminMode}
                      className="data-[state=checked]:bg-[#2864CE]"
                    />
                    <Label htmlFor="admin-mode" className="text-[#1952B6] font-medium">Режим тестирования</Label>
                  </div>
                </div>
              )}
            </div>
            <Button 
              variant="primary"
              fill="solid"
              size="m"
              onClick={handleCreateNewDesign}
              className="bg-[#2864CE] text-white hover:bg-[#1952B6]"
            >
              Новый чат
            </Button>
            <Button 
              variant="secondary"
              size="m"
              onClick={handleOpenDesignHistory}
            >
              История чата
            </Button>
          </div>
        </div>
        <Card className="flex-grow mb-0 shadow-lg border-[#2864CE] bg-white rounded-b-none">
          <ScrollArea className="h-[calc(100vh-280px)]">
            <CardContent>
              {messages.map((message) => (
                <div key={message.id} className={`mb-4 ${message.sender === 'user' ? 'text-right' : 'text-left'}`}>
                  <div className={`inline-block p-3 rounded-lg ${message.sender === 'user' ? 'bg-[#2864CE] text-white' : 'bg-[#EDEEEF] text-black'}`}>
                    {message.image ? (
                      <img src={message.image} alt="Загруженное изображение" className="max-w-full h-auto rounded" />
                    ) : (
                      <p className="text-sm whitespace-pre-wrap">{message.text}</p>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </ScrollArea>
        </Card>
        <div className="flex items-end gap-2 bg-white p-2 rounded-t-none rounded-b-lg">
          <Textarea 
            placeholder="Опишите ваш интерфейс..."
            value={input} 
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendAndGenerate()}
            onPaste={handlePaste}
            className="flex-grow bg-white text-black min-h-[80px] border-[#2864CE] rounded-lg"
          />
          <div className="flex gap-2">
            <Button 
              variant="secondary"
              fill="solid"
              size="m"
              onClick={handleAddImage}
              iconButton={<ImageIcon className="h-4 w-4" />}
            />
            <Button 
              variant="primary"
              fill="solid"
              size="m"
              onClick={handleSendAndGenerate} 
              disabled={isGeneratingUI}
              iconButton={<SendIcon className="h-4 w-4" />}
              className="bg-[#2864CE] text-white hover:bg-[#1952B6]"
            />
          </div>
        </div>
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleImageUpload}
          accept="image/*"
        />
      </div>
      {showDesign && (
        <div className={`${isFullscreen ? 'w-full' : 'w-1/2'} h-screen overflow-auto bg-[#EDEEEF] border-l border-[#2864CE] p-4 transition-all duration-300`}>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-[#0053A0]">Preview and Code</h2>
            <Button 
              variant="secondary"
              fill="outline"
              size="m"
              onClick={toggleFullscreen} 
              className="border-[#2864CE] text-[#1952B6] hover:bg-[#E6F0F9]"
            >
              {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>
          </div>

          <div className="space-y-4">
            {/* Preview Section */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h3 className="text-lg font-semibold text-[#0053A0] mb-2">Preview</h3>
              <div className="w-full h-[600px]">
                <iframe
                  src={getCodeSandboxUrl()}
                  style={{width:'100%', height:'100%', border:0, borderRadius: '4px', overflow:'hidden'}}
                  title="CodeSandbox Preview"
                  allow="accelerometer; ambient-light-sensor; camera; encrypted-media; geolocation; gyroscope; hid; microphone; midi; payment; usb; vr; xr-spatial-tracking"
                  sandbox="allow-forms allow-modals allow-popups allow-presentation allow-same-origin allow-scripts"
                />
              </div>
            </div>

            {/* Code Section */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <div className="mb-4 flex justify-between items-center">
                <h3 className="text-lg font-semibold text-[#0053A0]">Code</h3>
                <div className="flex space-x-2 overflow-x-auto">
                  {versions.map((version, index) => (
                    <Button
                      key={version.id}
                      variant={selectedVersion === version.id ? "primary" : "secondary"}
                      fill="solid"
                      size="s"
                      onClick={() => {
                        setSelectedVersion(version.id);
                        setEditableCode(version.code);
                        setCurrentVersion(index + 1);
                        updateIndexFile(version.code);
                      }}
                      className="flex-shrink-0"
                    >
                      V{index + 1}
                    </Button>
                  ))}
                </div>
                <div className="text-sm font-medium text-[#0053A0]">
                  Current: V{currentVersion}
                </div>
              </div>
              <div className="relative border-2 border-[#2864CE] rounded-lg overflow-hidden shadow-lg bg-white">
                <Editor
                  value={editableCode}
                  onValueChange={handleCodeChange}
                  highlight={(code) => highlight(code, languages.tsx, 'tsx')}
                  padding={20}
                  style={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontSize: 14,
                    lineHeight: 1.6,
                    height: 'calc(100vh - 600px)', // Adjusted height
                    overflow: 'auto',
                    backgroundColor: '#EDEEEF',
                    color: '#000',
                  }}
                  textareaClassName="focus:outline-none"
                  className="min-h-[300px] focus-within:shadow-outline-blue"
                />
                <div className="absolute top-4 right-4 flex gap-2">
                  <Button 
                    variant="secondary"
                    fill="outline"
                    size="m"
                    onClick={handleDownloadCode} 
                    className="bg-white text-[#0053A0] hover:bg-[#E6F0F9] border-[#0053A0]"
                    iconButton={<Download className="h-4 w-4" />}
                  />
                  <Button 
                    variant="secondary"
                    fill="outline"
                    size="m"
                    onClick={handleCopyCode} 
                    className="bg-white text-[#0053A0] hover:bg-[#E6F0F9] border-[#0053A0]"
                    iconButton={isCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UiGenerator