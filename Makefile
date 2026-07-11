CXX=g++
CXXFLAGS=-c -std=gnu++11 -W -Wall -Wextra -pedantic -MMD -MP -g3 -Og -Iinclude
LD=g++
LDFLAGS=
SOURCES_CPP=$(shell find src -name '*.cpp')
OBJECTS_CPP=$(SOURCES_CPP:src/%.cpp=obj/%.cpp.o)
OBJECTS=$(OBJECTS_CPP)
DEPENDENCIES_CPP=$(OBJECTS_CPP:obj/%.cpp.o=obj/%.cpp.d)
DEPENDENCIES=$(DEPENDENCIES_CPP)
MKDIR=mkdir -p
RM=rm -rf

ifeq ($(OS),Windows_NT)
	EXECUTABLE=bin/softmodem.exe
else
	EXECUTABLE=bin/softmodem
endif

all: $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	if [ ! -d $(dir $@) ]; then \
		$(MKDIR) $(dir $@); \
	fi

	$(LD) $^ $(LDFLAGS) -o $@

obj/%.cpp.o: src/%.cpp
	if [ ! -d $(dir $@) ]; then \
		$(MKDIR) $(dir $@); \
	fi

	$(CXX) $(CXXFLAGS) $< -o $@

clean:
	$(RM) obj bin

.PHONY: all clean

-include $(DEPENDENCIES)
